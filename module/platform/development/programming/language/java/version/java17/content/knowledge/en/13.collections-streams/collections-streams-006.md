# Local Records to Represent Intermediate Results in Collections and Streams (Java 17)

## 1. Why Do We Need a Data Type for Intermediate Results?

When processing collections, an input element often goes through several steps before producing the final output. For instance, from a list of orders, a program might compute revenue per customer, order count, validity status, or information used for sorting.

If an intermediate result has multiple related fields, temporary representations such as arrays, `Map.Entry`, or an auxiliary class declared at package level often make the data's meaning harder to read:

~~~java
Object[] summary = { "CUST-01", 4L, new BigDecimal("125.50") };
~~~

Readers must remember that index 0 is the customer ID, index 1 is the order count, and index 2 is the revenue. The compiler also cannot enforce specific types when retrieving values from `Object[]`.

A **local record** is a cleaner choice when a data type only needs to exist inside a single method or processing block. It gives clear names to each component and provides a constructor, accessors, `equals()`, `hashCode()`, and `toString()` generated automatically by Java.

Example:

~~~java
static void printSummary() {
    record CustomerTotal(
            String customerId,
            long orderCount,
            BigDecimal revenue) {
    }

    CustomerTotal total = new CustomerTotal(
            "CUST-01", 4, new BigDecimal("125.50"));

    System.out.println(total.customerId());
    System.out.println(total.orderCount());
    System.out.println(total.revenue());
}
~~~

`CustomerTotal` is declared only inside the `printSummary()` method. It does not become a public type in the package or external API. This is useful when you need a clear structure to pass data between steps of a collection/stream pipeline.

In Java 17, both records and local records are stable features; no preview flags are required.

## 2. Syntax and Scope of a Local Record

A local record is declared with the `record` keyword inside a block, typically a method body:

~~~java
static void process(List<String> values) {
    record ParsedValue(String original, String normalized) {
    }

    List<ParsedValue> parsed = values.stream()
            .map(value -> new ParsedValue(value, value.strip().toLowerCase()))
            .toList();

    parsed.forEach(System.out::println);
}
~~~

Rules to remember:

- A local record can only be used within the lexical scope where it is declared and appropriate nested blocks.
- You can create multiple instances, store them in local collections, use them as stream element types, or pass them to lambdas within that scope.
- The record automatically generates accessors named after its components, such as `original()` and `normalized()`.
- A record class is `final` and its components are `final`; you cannot subclass a record to add state.
- A local record is **implicitly static**. It holds no implicit reference to the enclosing instance and cannot directly read local variables or type parameters from the enclosing method the way a normal local class can.
- If the result type needs to be returned from the method, used as a field type, or shared across multiple methods, consider declaring the record at member or package level.

### 2.1. Local Records Can Have Constructors and Methods

Local records share the same core capabilities as other records: compact constructors for data validation, instance methods, and the ability to implement interfaces.

~~~java
static void showAmounts(List<BigDecimal> amounts) {
    record Amount(BigDecimal value, String currency) {
        Amount {
            Objects.requireNonNull(value, "value");
            Objects.requireNonNull(currency, "currency");
            if (currency.isBlank()) {
                throw new IllegalArgumentException("currency is blank");
            }
        }

        String display() {
            return value + " " + currency;
        }
    }

    amounts.stream()
            .map(value -> new Amount(value, "VND"))
            .map(Amount::display)
            .forEach(System.out::println);
}
~~~

Here, the record holds both the monetary amount and the currency unit together in a single value. The compact constructor guarantees that components are valid before an instance is created.

### 2.2. Local Records Do Not Capture Local Variables

Because a local record is implicitly static, its body cannot directly access local variables from the enclosing method:

~~~java
static void invalidCapture() {
    String currency = "VND";

    record Amount(BigDecimal value) {
        // Invalid: local record cannot capture the currency variable.
        // String display() { return value + " " + currency; }
    }
}
~~~

If an outer value needs to be part of the intermediate data, pass it into a component:

~~~java
static void validCaptureAlternative(List<BigDecimal> values) {
    String currency = "VND";

    record Amount(BigDecimal value, String currency) {
        String display() {
            return value + " " + currency;
        }
    }

    values.stream()
            .map(value -> new Amount(value, currency))
            .map(Amount::display)
            .forEach(System.out::println);
}
~~~

A lambda inside the method can capture `currency` if it is final or effectively final. It passes the value to the constructor; the record itself stores the data via its component. The record body only reads its own components.

### 2.3. Local Records in Generic Methods

A local record cannot directly use a type parameter from the enclosing method because it is implicitly static:

~~~java
static <T> void invalidGeneric(List<T> values) {
    // Invalid: local record cannot capture the method's T.
    // record Box(T value) {}
}
~~~

If you need a local generic type, declare a separate type parameter on the record:

~~~java
static <T> void printValues(List<T> values) {
    record Box<U>(U value) {
    }

    values.stream()
            .map(value -> new Box<T>(value))
            .map(Box::value)
            .forEach(System.out::println);
}
~~~

`Box<U>` has an independent type parameter. Inside the method, we instantiate `Box<T>`; `T` is passed as a type argument at the usage site rather than being captured by the record from the enclosing scope.

## 3. How Do Local Records Fit into Stream Pipelines?

A stream pipeline typically consists of three groups of operations:

1. **Data source:** collection, array, stream, or other source.
2. **Intermediate operations:** `map`, `filter`, `flatMap`, `sorted`, `distinct`, `peek`, etc. These describe how data is transformed/filtered and are typically executed lazily.
3. **Terminal operation:** `toList`, `collect`, `reduce`, `forEach`, `count`, etc. The terminal operation triggers processing.

Local records are very helpful when an intermediate operation produces a multi-field value, or when a collector needs to hold several related aggregated values.

~~~text
List<Order>
    |
    | stream()
    v
Stream<Order>
    |
    | grouping / map / filter
    v
Stream or Collector using LocalRecord
    |
    | collect() / toList()
    v
Aggregated result within method scope
~~~

For example, from an order you can compute an intermediate result row with product SKU, quantity, and line amount:

~~~java
static void printLineTotals(List<OrderLine> lines) {
    record LineTotal(String sku, long quantity, BigDecimal amount) {
    }

    List<LineTotal> totals = lines.stream()
            .map(line -> new LineTotal(
                    line.sku(),
                    line.quantity(),
                    line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity()))))
            .toList();

    totals.forEach(total -> System.out.printf(
            "%s: %d x -> %s%n",
            total.sku(), total.quantity(), total.amount()));
}
~~~

`LineTotal` lets subsequent steps read field names instead of remembering array element indices. An intermediate object can also be used to sort, filter, or group by a component.

## 4. Complete Example: Aggregating Revenue by Customer

Let us build a report from a collection of orders. Each order has a customer ID and a total amount. The output needs the customer ID, order count, and total revenue.

`Totals` is strictly internal data during aggregation inside `summarize`. Therefore, we declare it as a local record.

### 4.1. Input Model and Public Result

File `CustomerReport.java`:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public final class CustomerReport {
    private CustomerReport() {
    }

    public record Order(String customerId, BigDecimal total) {
        public Order {
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(total, "total");
            if (customerId.isBlank()) {
                throw new IllegalArgumentException(
                        "customerId must not be blank");
            }
        }
    }

    public record CustomerSummary(
            String customerId,
            long orderCount,
            BigDecimal revenue) {
    }

    public static List<CustomerSummary> summarize(List<Order> orders) {
        Objects.requireNonNull(orders, "orders");

        // This type is only needed inside the summarize method.
        record Totals(long orderCount, BigDecimal revenue) {
            Totals {
                Objects.requireNonNull(revenue, "revenue");
            }
        }

        Map<String, Totals> totalsByCustomer = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::customerId,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.mapping(
                                        Order::total,
                                        Collectors.reducing(
                                                BigDecimal.ZERO,
                                                BigDecimal::add)),
                                Totals::new)));

        return totalsByCustomer.entrySet().stream()
                .map(entry -> new CustomerSummary(
                        entry.getKey(),
                        entry.getValue().orderCount(),
                        entry.getValue().revenue()))
                .sorted(
                        Comparator.comparing(CustomerSummary::revenue)
                                .reversed()
                                .thenComparing(CustomerSummary::customerId))
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("CUST-01", new BigDecimal("100.00")),
                new Order("CUST-02", new BigDecimal("250.00")),
                new Order("CUST-01", new BigDecimal("75.50")),
                new Order("CUST-03", new BigDecimal("80.00")),
                new Order("CUST-02", new BigDecimal("50.00")));

        summarize(orders).forEach(System.out::println);
    }
}
~~~

In Java 17, `Collectors.teeing()` has been available since Java 12. It runs two collectors on the same group of elements and combines the two results using a merge function. Here:

- `counting()` counts the orders in the group.
- `mapping(Order::total, reducing(...))` computes the sum of order totals.
- `Totals::new` takes both results and creates a local record holding them together.

After grouping, the map conceptually looks like:

~~~text
"CUST-01" -> Totals(orderCount=2, revenue=175.50)
"CUST-02" -> Totals(orderCount=2, revenue=300.00)
"CUST-03" -> Totals(orderCount=1, revenue=80.00)
~~~

Then the entries are streamed to convert into `CustomerSummary`, sorted by revenue descending and by customer ID ascending when revenues tie.

### 4.2. Why Use the Local Record `Totals`?

If `Object[]` were used, readers would have to know which index is count and which is revenue. If `Map.Entry<Long, BigDecimal>` were used, the meaning of the two parts would still be less clear than domain names. A local record expresses the structure directly:

~~~java
record Totals(long orderCount, BigDecimal revenue) {
}
~~~

At the same time:

- The type appears only inside `summarize`, where it is created and consumed.
- It does not bloat the package with extra top-level types.
- It provides strongly typed accessors: `orderCount()` and `revenue()`.
- It logs cleanly via auto-generated `toString()`.
- It supports value equality via component-based `equals()` and `hashCode()`.

`CustomerSummary`, by contrast, is declared at member level because it is the public result type returned by the method. This is a useful boundary: **internal intermediate types are local records; result types exported from a method have broader scope**.

### 4.3. Execution Output

Compile and run:

~~~text
javac --release 17 -encoding UTF-8 CustomerReport.java
java CustomerReport
~~~

Output:

~~~text
CustomerSummary[customerId=CUST-02, orderCount=2, revenue=300.00]
CustomerSummary[customerId=CUST-01, orderCount=2, revenue=175.50]
CustomerSummary[customerId=CUST-03, orderCount=1, revenue=80.00]
~~~

`BigDecimal` is used for money instead of `double` to avoid binary floating-point representation errors common in decimal calculations. The example assumes all input values share the same currency and rounding rules; real applications must model currency and rounding policies if multiple currencies exist.

## 5. Local Records in Other Processing Steps

### 5.1. `map`: Transforming One Element into a Multi-Field Result

~~~java
static List<String> normalizeNames(List<String> names) {
    record NormalizedName(String original, String value, boolean changed) {
    }

    return names.stream()
            .map(name -> {
                String normalized = name.strip().toLowerCase(Locale.ROOT);
                return new NormalizedName(
                        name, normalized, !name.equals(normalized));
            })
            .filter(NormalizedName::changed)
            .map(NormalizedName::value)
            .toList();
}
~~~

`NormalizedName` keeps the original value, normalized value, and a flag indicating whether it changed together. Subsequent steps can filter by `changed()` and then extract `value()`.

### 5.2. `filter`: Keeping Validated Results

~~~java
static void printParsedScores(List<String> inputs) {
    record ParsedScore(String source, int value) {
    }

    inputs.stream()
            .map(input -> {
                try {
                    return Optional.of(
                            new ParsedScore(input, Integer.parseInt(input)));
                } catch (NumberFormatException exception) {
                    return Optional.<ParsedScore>empty();
                }
            })
            .flatMap(Optional::stream)
            .filter(parsed -> parsed.value() >= 0 && parsed.value() <= 100)
            .forEach(System.out::println);
}
~~~

`Optional.stream()` has existed since Java 9, so it works in Java 17. This avoids `null` elements in the stream. The record keeps the source string alongside the parsed result; downstream steps only receive elements that parsed successfully.

### 5.3. `sorted`: Keeping the Sort Key Together with Data

~~~java
static void printByNormalizedName(List<String> names) {
    record SortKey(String original, String normalized) {
    }

    names.stream()
            .map(name -> new SortKey(
                    name, name.strip().toLowerCase(Locale.ROOT)))
            .sorted(Comparator.comparing(SortKey::normalized))
            .map(SortKey::original)
            .forEach(System.out::println);
}
~~~

The local record holds the comparison key and the original value together. After sorting, the program retrieves the original value for display.

### 5.4. `flatMap`: Representing Split Elements

Suppose each log line contains an order ID and multiple tags. You can use a local record to retain source metadata while flattening the list:

~~~java
static List<String> allTags(List<LogLine> lines) {
    record TaggedValue(String orderId, String tag) {
    }

    return lines.stream()
            .flatMap(line -> line.tags().stream()
                    .map(tag -> new TaggedValue(line.orderId(), tag)))
            .filter(value -> value.tag() != null && !value.tag().isBlank())
            .map(TaggedValue::tag)
            .toList();
}
~~~

The local record preserves `orderId` and `tag` across `flatMap`; if later steps need to group tags by order, the source information remains available. If only the final tag is needed and `orderId` is unused, the record may be unnecessary; avoid adding intermediate types that carry no meaning.

## 6. Comparing Local Records with Other Representations

| Representation | Pros | Cons | When appropriate |
|---|---|---|---|
| Local record | Named components, explicit types, auto-generated `equals/hashCode/toString`, narrow scope. | Cannot be used as a public return type outside its declaration scope; implicitly static. | Intermediate results used only inside one method/block. |
| Member-level record | Has record features and is reusable across multiple methods of a class. | Broader scope than needed if used in only one place. | Result types shared within one class or API. |
| Top-level record | Usable across multiple classes/packages and as an API type. | Adds another package/module-level type. | Domain data or widely shared results. |
| `Map.Entry<K,V>` | Built-in, convenient for key/value pairs. | Only represents two components; key/value names may not convey business semantics. | An actual key/value pair. |
| Arrays (`Object[]`, `long[]`) | Minimal syntax, can be compact in low-level calculations. | No field names; error-prone indexing/casting; potentially mutable. | Low-level numeric data with fixed, well-known layout. |
| Regular class | Customizable mutability, inheritance, lifecycle, and complex logic. | More boilerplate than a record. | Objects with behavior, mutable state, or complex lifecycles. |

A local record is not always better than a simple variable. If the result is just a `long`, use `long`. If you have two independent values without needing a new type, `Map.Entry` may suffice. Use a local record when **a group of fields carries shared meaning and is processed as a unit**.

## 7. Limitations and Notes When Using in Collections/Streams

### 7.1. Record Components Are Only Shallowly Immutable

A record has final components, but that does not automatically make referenced objects immutable:

~~~java
record Snapshot(List<String> tags) {
}
~~~

The `tags` reference is final, but the inner list can still be mutated if the caller retains a mutable reference. If you need a snapshot that cannot be mutated through the accessor, copy it in the constructor:

~~~java
record Snapshot(List<String> tags) {
    Snapshot {
        tags = List.copyOf(tags);
    }
}
~~~

`List.copyOf` creates an unmodifiable list and rejects `null` elements. This is a good fit if the data contract requires the tag list to be null-free.

### 7.2. Do Not Let a Local Record Escape Its Declaration Scope

A local record has narrow scope. You cannot declare another method outside the block and use the local record's type name as a parameter or return type:

~~~java
static void example() {
    record Intermediate(long count) {
    }

    Intermediate value = new Intermediate(10);
    System.out.println(value.count());
}

// Cannot write a class-level method accepting Intermediate,
// because the type name Intermediate is not in scope here.
~~~

If you need to pass the result to another class, promote it to an appropriate scope such as a member/top-level record, or convert it to a DTO/API model at the method boundary.

### 7.3. Local Records Are Not an Automatic Performance Optimization

Records improve code clarity, but do not assume they are always faster than classes or arrays. Each record instantiation can still allocate an object; the JVM may optimize some allocations via JIT/escape analysis, but do not rely on that without measuring.

For very large pipelines, benchmark on representative data and inspect allocation/GC if performance is a critical requirement. Do not switch to `Object[]` out of premature concern before seeing measurements; named structures typically reduce maintenance bugs.

### 7.4. Do Not Use Stream Side Effects to Populate Intermediate Data

Avoid creating an external collection and using `forEach` to add data to it:

~~~java
// Do not use side effects as the default way to transform a stream.
List<String> output = new ArrayList<>();
values.stream().forEach(value -> output.add(value.strip()));
~~~

Use `map(...).toList()` or `collect(...)`. Local records help each `map` step return a structured value, making pipelines easier to read and freer of side effects.

## 8. When Should a Local Record Become a Shared Record?

A local record is appropriate when:

- Only a single method creates and consumes that data.
- Component names clarify `map`, `filter`, `collect`, and `sorted` steps.
- The type is not part of a public contract.
- The intermediate data has a stable structure within the processing scope.

Promote it to a member-level or top-level record if:

- Multiple methods or multiple classes need the same type.
- It is the return type of an API, service, or repository.
- Unit tests need to reference that type directly from another package.
- It represents an independently meaningful domain concept.
- The structure needs to be documented, serialized, or exchanged across modules.

For example, `Totals` in `CustomerReport.summarize()` is a local record because it only serves the collector. `CustomerSummary` is returned from the method and must therefore have broader scope.

## 9. Testing Logic That Creates Intermediate Results

A record automatically generates `equals()` and `hashCode()` based on its components, making value assertions convenient:

~~~java
record Totals(long count, BigDecimal revenue) {
}

Totals actual = new Totals(2, new BigDecimal("175.50"));
Totals expected = new Totals(2, new BigDecimal("175.50"));

assertEquals(expected, actual);
~~~

In real test code, if a local record is declared inside a production method, external tests cannot name that local type directly. Test through the method's public output or extract the computation into a method with an appropriate return type.

For `CustomerReport`, you can verify:

- Each customer has the exact order count.
- Total revenue equals the sum of that customer's orders.
- Results are sorted by revenue descending.
- When revenues tie, customer IDs are sorted ascending.
- An empty input list produces an empty result list.
- `null` input is rejected per the `Objects.requireNonNull` contract.

Empty input example:

~~~java
List<CustomerReport.CustomerSummary> empty =
        CustomerReport.summarize(List.of());

if (!empty.isEmpty()) {
    throw new AssertionError("Expected empty summary");
}
~~~

Local records make aggregation steps clear to implement; tests still need to verify final outputs against business requirements.

## 10. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Cannot use local record name in another method | The type is only scoped to its declaring block. | Move the record to member/top-level scope if reuse is needed. |
| Local record cannot access local variables | Local records are implicitly static and do not capture enclosing variables. | Pass values into components or compute them when instantiating. |
| Using a method's type parameter inside a local record | Local records do not capture type parameters from enclosing methods. | Declare the record's own type parameter, e.g., `record Box<U>(U value)`. |
| Data inside the record still mutates | Final components only freeze the reference, not inner object mutability. | Copy collections or use data types with immutable contracts. |
| Using `Object[]` for multi-field results | Lacks component names and requires manual casting. | Use a local record with meaningful field names. |
| Using a local record for just a single value | Unnecessary type creation. | Use a simple type if there is no group of fields needing names. |
| Collector fails to combine two results | Merge function signature or generic types do not match. | Verify return types of each collector and the local record constructor. |
| Calling `List.get(i)` in a stream over `LinkedList` | Index-based access can take linear time per lookup. | Stream the list directly or use an appropriate iterator/stream. |
| Using `double` for money | Decimal representation errors can accumulate. | Use `BigDecimal` with explicit scale/rounding rules. |

## 11. Practice Exercises

### Exercise 1 — Create Parsed Results

Given a list of strings representing quantities. Declare a local record `ParsedQuantity(String source, int quantity)` inside the processing method. Use a stream to parse each string, keep only values from 1 to 100, and print both the original string and the parsed integer.

### Exercise 2 — Aggregate by Product Category

Given a list of `ProductSale(category, amount)`. Use a local record `CategoryTotal(long count, BigDecimal revenue)` to group by category, count rows, and sum amounts with a collector.

### Exercise 3 — Create a Sort Key

Given a list of usernames. Use a local record holding `originalName` and `normalizedName`, sort by `normalizedName`, and then print `originalName`. Choose an appropriate locale when normalizing technical identifiers.

### Exercise 4 — Verify Capture Limits

Write a generic method `<T>` and try declaring a local record with a component of type `T`. Observe the compilation error, then fix it by declaring a separate generic local record such as `record Box<U>(U value)`.

### Exercise 5 — Decide Type Scope

Suppose `CustomerSummary` is only used inside one reporting method. Consider keeping it as a local record. Then suppose three other services also accept and return `CustomerSummary`; explain why it should be promoted to a member/top-level record.

### Self-Check Hints

- Exercise 1: The local record stores source data and the parsed value; catch `NumberFormatException` or use `Optional` to represent errors.
- Exercise 2: You can use `groupingBy` combined with `teeing(counting(), mapping(... reducing(...)), CategoryTotal::new)`.
- Exercise 3: Normalize with `toLowerCase(Locale.ROOT)` if the name is used as a locale-independent technical key.
- Exercise 4: Local records are implicitly static; a generic record must declare its own type parameter.
- Exercise 5: A type's scope should reflect its usage scope; types exchanged across services should not be hidden inside a single method.

## 12. Principles to Remember

- A local record is a record declared inside a block, usually within a method.
- It is well suited for representing multi-component intermediate results in collection and stream pipelines.
- Components have clear names and types, replacing cryptic arrays or generic pairs.
- Local records are implicitly static and do not capture the enclosing instance, local variables, or method type parameters.
- If external data is needed, pass it through the constructor/components; lambdas instantiating the record can still use effectively final method variables.
- Records are shallowly immutable: final components do not automatically make inner collections immutable.
- A local record cannot be used as a return or field type outside its declaration scope. If sharing is required, promote it to a member or top-level record.
- `map`, `filter`, `flatMap`, `sorted`, and `collect` pair naturally with local records to build readable pipelines with fewer side effects.
- Use `BigDecimal` for money and specify rounding/currency rules in real business logic.
- Do not add a local record when a simple type suffices; use it when component names genuinely clarify the data.

### References

- [Java SE 17 Language Specification — Section 8.10: Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [Java SE 17 Language Specification — Section 14.3: Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3).
- [Java SE 17 API — Collectors.teeing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#teeing(java.util.stream.Collector,java.util.stream.Collector,java.util.function.BiFunction)).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
