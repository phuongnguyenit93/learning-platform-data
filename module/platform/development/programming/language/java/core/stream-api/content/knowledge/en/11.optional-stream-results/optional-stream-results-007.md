# Combining Search Results With Subsequent Pipelines

> **Chapter:** Optional in Stream Results  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API via lazy pipelines, `filter`, `map`, `reduce`, `collect`, along with grouping techniques, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers. Pay attention to state, resources, and performance when building pipelines.

A very common question when processing data is: **After finding an object with a Stream, how do we continue filtering, transforming, or traversing data related to that object?** For example, we find a paid order and then look up the corresponding customer; or we find an order and list the product codes from its line items.

Stream search operations typically return `Optional<T>`, because a result cannot be guaranteed. To chain safely, distinguish three situations:

1. **Transforming a potentially absent result:** use `Optional.map`.
2. **Transitioning from one search result to another search result:** use `Optional.flatMap`.
3. **Bringing a potentially absent result back into a Stream pipeline:** use `Optional.stream()` (Java 9+).

This lesson uses Java 17+ syntax, and explains how to handle empty sources, `null` values, `findFirst`/`findAny`, `min`/`max`, and the cost of nested searches.

## 1. Why Is a Search Result an `Optional`?

Consider an example finding a product by code:

```java
import java.util.List;
import java.util.Optional;

record Product(String code, String name, int price) {}

List<Product> products = List.of(
        new Product("P-01", "Notebook", 40_000),
        new Product("P-02", "Pen", 15_000),
        new Product("P-03", "Briefcase", 180_000)
);

Optional<Product> found = products.stream()
        .filter(p -> p.code().equals("P-02"))
        .findFirst();
```

After `filter`, the Stream may have one or more elements left, or no elements left at all. `findFirst()` is a **terminal operation**: it ends the pipeline and returns an `Optional<Product>`, which may contain the found product or be empty if no product matches.

| Terminal operation on `Stream<T>` | Result type | Meaning |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | Gets the first element in encounter order, if present. |
| `findAny()` | `Optional<T>` | Gets any element; may differ during parallel processing. |
| `min(comparator)` | `Optional<T>` | Gets a smallest element according to the comparator. |
| `max(comparator)` | `Optional<T>` | Gets a largest element according to the comparator. |

For primitive streams, the corresponding search/extremum operations return `OptionalInt`, `OptionalLong`, or `OptionalDouble`, rather than `Optional<Integer>`, `Optional<Long>`, or `Optional<Double>`.

**Distinguishing Stream and Optional objects:** `Stream<T>` can hold multiple elements and usually processes lazily; `Optional<T>` represents only **zero or one value**. `Optional.map` or `Optional.flatMap` applies immediately to the held value if non-empty; they are not lazy intermediate Stream operations.

## 2. `Optional.map`: Transforming a Search Result

If a product is found but you only need its name, use `map` on the `Optional<Product>` result:

```java
Optional<String> productName = found.map(Product::name);

System.out.println(productName.orElse("Not found"));
// Pen
```

If `found` is `Optional.empty()`, `Product::name` **is not called** and `productName` is also empty. There is no need to call `get()` or write `if (found.isPresent())` for manual access.

A chain of transformations can be written directly:

```java
String label = products.stream()
        .filter(p -> p.code().equals("P-02"))
        .findFirst()                       // Optional<Product>
        .map(Product::name)               // Optional<String>
        .map(name -> name.toUpperCase())  // Optional<String>
        .orElse("NOT FOUND");             // String

System.out.println(label); // PEN
```

Notice how the return type changes at each step: `findFirst` does not return `Product`, `map(Product::name)` does not return `String`, and `orElse(...)` is the step that unwraps into `String`.

With `Optional.map`, if the mapper returns `null`, the result becomes `Optional.empty()`. However, you should define a clear missing-data policy rather than silently relying on this behavior when `null` is a data error.

### Adding a Condition With `Optional.filter`

When you already have a candidate and need to check an additional condition:

```java
Optional<Product> affordable = found
        .filter(p -> p.price() <= 20_000);

System.out.println(affordable.map(Product::code).orElse("not qualified"));
// P-02
```

`Optional.filter(predicate)` checks **at most one** held value. If the predicate is false, the result is `Optional.empty()`. It differs from `Stream.filter(predicate)`, which can check many elements in a data source.

## 3. `Optional.flatMap`: Chaining Two Search Steps

Suppose an order has been found. Each order has a `customerId`; the next step is to find the corresponding customer object.

```java
Optional<Order> order = orders.stream()
        .filter(o -> o.id().equals(requestedId))
        .findFirst();

// Finding the customer produces another Optional<Customer>.
Optional<Customer> customer = order.flatMap(o ->
        customers.stream()
                .filter(c -> c.id().equals(o.customerId()))
                .findFirst()
);
```

The snippet above uses `Order`, `Customer`, `orders`, `customers`, and `requestedId`, which are fully defined in the program in section 5.

Why use `flatMap` instead of `map`? Because the callback for the second search **already returns `Optional<Customer>`**:

```java
// map creates an Optional nested inside an Optional:
Optional<Optional<Customer>> nested = order.map(o ->
        customers.stream()
                .filter(c -> c.id().equals(o.customerId()))
                .findFirst()
);

// flatMap flattens it down to a single Optional layer:
Optional<Customer> flattened = order.flatMap(o ->
        customers.stream()
                .filter(c -> c.id().equals(o.customerId()))
                .findFirst()
);
```

Selection rules:

| Situation | Operation | Result type |
| --- | --- | --- |
| Function `T -> U` | `Optional<T>.map(...)` | `Optional<U>` |
| Function `T -> Optional<U>` | `Optional<T>.flatMap(...)` | `Optional<U>` |
| Function `T -> boolean` | `Optional<T>.filter(...)` | `Optional<T>` |

If `order` is empty, the lambda inside `flatMap` does not run, so no customer search occurs. If the order exists but the customer is not found, `flatMap` returns `Optional.empty()`. `Optional.flatMap` requires the mapper to return a **non-null** `Optional` object; a mapper returning `null` causes `NullPointerException`.

## 4. `Optional.stream()`: Converting Back to a 0-or-1-Element Pipeline

Since Java 9, `Optional<T>` has the method:

```java
Stream<T> stream()
```

It creates a Stream containing **one element** if the Optional has a value, or an **empty** Stream if the Optional is empty. This serves as a bridge to continue using Stream operations such as `flatMap`, `filter`, `map`, `distinct`, `sorted`, and `toList`.

```java
import java.util.Optional;

List<String> present = Optional.of("java").stream()
        .map(String::toUpperCase)
        .toList();
// [JAVA]

List<String> absent = Optional.<String>empty().stream()
        .map(String::toUpperCase)
        .toList();
// []
```

Distinguish `optional.stream()` from `collection.stream()`:

- `collection.stream()` can contain all elements of the collection.
- `optional.stream()` has at most one element, which is the value held inside the Optional.
- When the value held inside the Optional **is a collection**, you must call an additional `flatMap` or other steps to traverse **the elements of that collection**.

Example:

```java
Optional<List<Integer>> maybeNumbers = Optional.of(List.of(5, 3, 8));

List<Integer> values = maybeNumbers.stream()   // Stream<List<Integer>>
        .flatMap(List::stream)                 // Stream<Integer>
        .filter(n -> n > 4)
        .sorted()
        .toList();

// [5, 8]
```

If you write `maybeNumbers.stream().map(List::size)`, you only get the size of the held list, instead of traversing the numbers inside.

## 5. Complete Example: Finding an Order, Finding the Customer, and Processing Line Items

The Java 17+ example below illustrates **two continuation paths from the same `Optional<Order>`**: looking up the customer with `flatMap`, and converting back to a Stream to process multiple line items with `Optional.stream()`. Save as `OptionalPipelineDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class OptionalPipelineDemo {
    record LineItem(String sku, int quantity) {}
    record Order(
            String id,
            String customerId,
            boolean paid,
            List<LineItem> items
    ) {}
    record Customer(String id, String name, boolean active) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("OD-101", "C-01", true, List.of(
                        new LineItem("BOOK", 2),
                        new LineItem("PEN", 4))),
                new Order("OD-102", "C-02", false, List.of(
                        new LineItem("PEN", 1))),
                new Order("OD-103", "C-03", true, List.of(
                        new LineItem("BOOK", 1),
                        new LineItem("BAG", 1)))
        );

        List<Customer> customers = List.of(
                new Customer("C-01", "An", true),
                new Customer("C-02", "Bình", true),
                new Customer("C-03", "Chi", false)
        );

        String requestedId = "OD-101";
        Optional<Order> foundPaidOrder = orders.stream()
                .filter(o -> o.id().equals(requestedId))
                .filter(Order::paid)
                .findFirst();

        // Optional<Order> -> Optional<Customer> -> Optional<String>
        Optional<String> customerName = foundPaidOrder
                .flatMap(order -> customers.stream()
                        .filter(c -> c.id().equals(order.customerId()))
                        .filter(Customer::active)
                        .findFirst())
                .map(Customer::name);

        // Optional<Order> -> Stream<Order> -> Stream<LineItem>
        List<String> skus = foundPaidOrder.stream()
                .flatMap(o -> o.items().stream())
                .filter(item -> item.quantity() > 0)
                .map(LineItem::sku)
                .distinct()
                .sorted()
                .toList();

        // Case where no order is found.
        Optional<Order> missing = orders.stream()
                .filter(o -> o.id().equals("OD-999"))
                .findFirst();
        List<String> skusWhenMissing = missing.stream()
                .flatMap(o -> o.items().stream())
                .map(LineItem::sku)
                .toList();

        System.out.println("Customer: "
                + customerName.orElse("No active customer found"));
        System.out.println("SKUs: " + skus);
        System.out.println("No order: " + skusWhenMissing);
    }
}
```

Output:

```text
Customer: An
SKUs: [BOOK, PEN]
No order: []
```

Data flow of the example:

```text
orders.stream()
     │
     └── filter(id + paid)
                    │
                    └── findFirst() ──► Optional<Order>
                                             │
                      ┌──────────────────────┴────────────────────────┐
                      │                                               │
             flatMap(find customer)                            stream()
                      │                                               │
              Optional<Customer>                             Stream<Order> (0..1)
                      │                                               │
                map(Customer::name)                           flatMap(items.stream)
                      │                                               │
              Optional<String>                               Stream<LineItem> (0..n)
                      │                                               │
                 orElse(...)                                 filter/map/distinct/sorted
                      │                                               │
                    "An"                                        [BOOK, PEN]
```

Note that `foundPaidOrder` is an **Optional**, so you can call `map` or `stream()` on it multiple times. Each call to `foundPaidOrder.stream()` creates a new Stream; each individual Stream remains a **single-use object** that must not be reused after a terminal operation.

If `requestedId` does not exist, `foundPaidOrder` is empty: the customer lookup path does not invoke the inner functions, and the line-item traversal path returns an empty list. This avoids creating a dummy `Order` object or writing manual `null` checks.

## 6. Combining Multiple Search Results With `Stream<Optional<T>>`

Sometimes you need to look up **multiple input IDs**, not all of which exist. A clear way to express this is to `map` each ID to `Optional<Order>`, then use `flatMap(Optional::stream)` to discard empty results and keep the found objects:

```java
List<String> requestedIds = List.of("OD-101", "OD-999", "OD-103");

List<String> paidOrderIds = requestedIds.stream()
        .map(id -> orders.stream()
                .filter(o -> o.id().equals(id))
                .findFirst())              // Stream<Optional<Order>>
        .flatMap(Optional::stream)         // Stream<Order>
        .filter(Order::paid)
        .map(Order::id)
        .toList();

System.out.println(paidOrderIds);
// [OD-101, OD-103]
```

**How does `flatMap(Optional::stream)` work?** For each Optional, it gets a Stream of 0 or 1 element and concatenates the sub-Streams. The result is a Stream containing only the found orders.

| Search ID | `findFirst()` result | After `Optional.stream()` |
| --- | --- | --- |
| OD-101 | `Optional[Order(...)]` | One `Order` |
| OD-999 | `Optional.empty()` | No element |
| OD-103 | `Optional[Order(...)]` | One `Order` |

In these snippets, `orders` and the `record` types are the data from the program in section 5. Writing `orders.stream()` **inside** the lambda creates a new lookup Stream for each ID. This is valid when `orders` is a `List`, yet can be slow when the data volume is large.

### Cost of Repeated Lookups

If there are `m` IDs and `n` orders, each call to `orders.stream().filter(...).findFirst()` may scan up to `n` orders. The total worst-case cost can approach **O(m × n)**.

For a large number of IDs, building an index beforehand for roughly O(1) average lookup by ID is a better approach:

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

// Requires Order ids to be unique.
Map<String, Order> orderById = orders.stream()
        .collect(Collectors.toMap(Order::id, Function.identity()));

List<String> ids = requestedIds.stream()
        .map(id -> Optional.ofNullable(orderById.get(id)))
        .flatMap(Optional::stream)
        .filter(Order::paid)
        .map(Order::id)
        .toList();

// [OD-101, OD-103]
```

`Collectors.toMap` here throws `IllegalStateException` if there are duplicate order IDs; choose a duplicate-key policy if the real source does not guarantee uniqueness. When looking up only a few IDs, using `findFirst()` directly is usually easier to read and requires no index creation.

## 7. Handling Empty Optionals and Fallback Strategies

To chain pipelines safely, **defer unwrapping the Optional** until the point where business logic genuinely needs the unwrapped value. Commonly used methods:

| Method | When Optional has a value | When Optional is empty |
| --- | --- | --- |
| `map(f)` | Transforms the value using `f` | Returns an empty Optional |
| `flatMap(f)` | Calls `f` and receives a new Optional | Returns an empty Optional |
| `filter(p)` | Keeps the value when `p` is true | Returns an empty Optional |
| `stream()` | Returns a Stream with one element | Returns an empty Stream |
| `ifPresent(action)` | Executes action | Does not execute action |
| `orElse(value)` | Gets the present value | Gets `value` |
| `orElseGet(supplier)` | Gets the present value | Calls supplier to get the value |
| `or(supplier)` | Keeps the current Optional | Calls supplier returning a replacement Optional (Java 9+) |
| `orElseThrow(...)` | Gets the value | Throws an exception |

Example using a default value:

```java
String name = customerName.orElse("Unknown customer");
```

### `orElse` Differs From `orElseGet`

`orElse` accepts **a value evaluated before** calling the method, even when the Optional already has a value. `orElseGet` only invokes the supplier when the Optional is empty:

```java
String label = customerName.orElseGet(() -> createFallbackLabel());
```

Here, `createFallbackLabel()` is an illustrative method name supplied by the application. If computing the fallback label consumes resources or has side effects, `orElseGet` avoids unnecessary calls. If it is just a fixed string, `orElse("...")` is enough.

If you want to **search a fallback source**, `Optional.or` (Java 9+) preserves the Optional type without forcing a value yet:

```java
Optional<Product> result = products.stream()
        .filter(p -> p.code().equals("P-999"))
        .findFirst()
        .or(() -> products.stream()
                .filter(p -> p.price() <= 20_000)
                .findFirst());

// Optional containing P-02 from the fallback search.
```

The supplier of `or` runs only when the primary search returns an empty Optional. This is a clean way to chain two search sources when the second source is a fallback, rather than a transformation of the result from the first source.

### When Should You Throw an Exception?

```java
Order required = orders.stream()
        .filter(o -> o.id().equals(requestedId))
        .findFirst()
        .orElseThrow(() -> new IllegalArgumentException(
                "Order does not exist: " + requestedId));
```

Use `orElseThrow` when missing data is an error that must be reported immediately. If missing data is a normal situation (such as a user searching for a nonexistent code), continuing to return `Optional`, an empty list, or a fallback message is more appropriate. Avoid calling `get()` unchecked, as it throws `NoSuchElementException` when the Optional is empty.

## 8. How Do `OptionalInt`, `OptionalLong`, and `OptionalDouble` Connect?

`IntStream.findFirst()`, `IntStream.max()`, and `IntStream.min()` return `OptionalInt`; `LongStream` and `DoubleStream` have their respective specialized Optionals.

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt largest = IntStream.of(3, 8, 5).max();

int doubled = largest.stream()
        .map(n -> n * 2)
        .findFirst()
        .orElse(0);

System.out.println(doubled); // 16
```

Since Java 9, `OptionalInt.stream()` creates an `IntStream` containing 0 or 1 element; `OptionalLong.stream()` and `OptionalDouble.stream()` behave similarly. Primitive Optionals **do not have the full API of `Optional<T>`**: for instance, in Java 17, `OptionalInt` has no generic `map` and `flatMap`. If you need a transformation pipeline, convert to a primitive stream with `.stream()` and then call `IntStream.map` or other operations.

When the input is a `Stream<OptionalInt>`, you can flatten it into a primitive stream:

```java
List<OptionalInt> matches = List.of(
        OptionalInt.of(4),
        OptionalInt.empty(),
        OptionalInt.of(7)
);

int sum = matches.stream()
        .flatMapToInt(OptionalInt::stream)
        .sum();

System.out.println(sum); // 11
```

This avoids boxing when computing a sum. If the problem only needs a replacement value, `largest.orElse(0)` is usually shorter.

## 9. Common Misconceptions About Lifecycle, Order, and `null`

### The Terminal Operation Has Already Ended the Old Stream

```java
// Stream<Order> pipeline = orders.stream().filter(Order::paid);
// Optional<Order> first = pipeline.findFirst();
// pipeline.filter(o -> o.id().startsWith("OD-")); // Invalid
```

After `findFirst`, `pipeline` has been consumed; you must not call further operations on **the same Stream object**. To continue processing the found element, use `first.map(...)`, `first.flatMap(...)`, or `first.stream()`. To traverse the **source** again, create a new Stream if the source supports it. For single-read I/O sources, plan differently and close resources according to their lifecycle.

### `findFirst` and `findAny` Have Different Contracts

On an ordered `List`, `findFirst` returns the first matching element in encounter order. `findAny` is allowed to return **any matching element**, which is useful when the application has no positional preference and especially when running in parallel. Do not use `findAny` if business results depend on the first record.

If you subsequently `flatMap` into another search, choosing differently in the first step can lead to a different final result. Decide clearly whether to pick the first record or any record.

### Optional Does Not Automatically Fix `null` Data

Do not treat `Optional` as a mechanism that automatically repairs broken source data:

```java
import java.util.Objects;

List<String> namesWithNull = java.util.Arrays.asList(
        null, "An", "Bình");

Optional<String> firstValid = namesWithNull.stream()
        .filter(Objects::nonNull)
        .findFirst();
```

`findFirst`/`findAny` can throw `NullPointerException` if the selected element is `null`; in the example above, `Objects::nonNull` removes those values before searching. `Optional.of(null)` also throws `NullPointerException`, while `Optional.ofNullable(null)` creates `Optional.empty()`. At boundaries where missing data is intentional, `ofNullable` is more appropriate.

### `Optional` Does Not Mean Anything Goes With Side Effects

The `map`/`flatMap` operations on Optional work on the present value; however, if their callbacks open I/O sources, mutate shared data, or depend on time, repeating them can yield different results. Within nested Streams, lambdas should not interfere with the source and should avoid mutable state, especially with `parallelStream()`.

## 10. Choosing the Right Way to Chain Pipelines

| Need | Usually suitable expression | Reason |
| --- | --- | --- |
| Find an order then get customer ID | `findFirst().map(Order::customerId)` | Transformation function returns a direct value. |
| Find an order then find the customer object | `findFirst().flatMap(o -> customers.stream()...findFirst())` | Second lookup function returns Optional. |
| Find an order then iterate its line items | `findFirst().stream().flatMap(o -> o.items().stream())` | Back to a Stream of 0 or 1 order, then expand into 0 or more line items. |
| Look up many IDs, skipping nonexistent ones | `map(id -> lookup(id)).flatMap(Optional::stream)` | Flattens a Stream containing many Optionals. |
| Search a fallback when no result is found | `findFirst().or(() -> alternativeFind())` | Keeps Optional type; runs fallback search when needed. |
| Need only a display value, with default | `findFirst().map(...).orElse("N/A")` | Converts to a regular type at the display boundary. |
| Missing data is an error | `findFirst().orElseThrow(...)` | Makes mandatory preconditions explicit. |

Choose the approach based on **the return type of the next step** and the number of elements to process; do not unwrap the Optional immediately upon finding a result by default.

## 11. Self-Check Exercises

**Exercise 1 — Transforming a search result.** Given `Optional<String> value = Optional.of("java")`. Write an expression producing an `Optional<Integer>` containing the string length.

```java
Optional<Integer> length = value.map(String::length);
// Optional[4]
```

**Exercise 2 — Nested search results.** Why does `order.map(o -> customers.stream().filter(...).findFirst())` have type `Optional<Optional<Customer>>`?

**Answer:** `findFirst` on the second Stream already returns `Optional<Customer>`. `Optional.map` wraps that result in another Optional. Use `flatMap` if you want to obtain `Optional<Customer>` directly.

**Exercise 3 — Optional with no data.** What is the result of the following snippet?

```java
List<Integer> result = Optional.<Integer>empty()
        .stream()
        .map(n -> n * 10)
        .toList();
```

**Answer:** An empty list `[]`. The pipeline does not invoke the mapper because the Stream has no elements.

**Exercise 4 — Multiple Optionals.** Given `[Optional.of(2), Optional.empty(), Optional.of(5)]`, how do you get the sum `7` without calling `get()`?

```java
int total = List.of(Optional.of(2), Optional.<Integer>empty(), Optional.of(5))
        .stream()
        .flatMap(Optional::stream)
        .mapToInt(Integer::intValue)
        .sum();
// 7
```

**Exercise 5 — Distinguishing Stream and Optional.** Is the snippet below valid?

```java
// Stream<String> s = List.of("An", "Bình").stream();
// Optional<String> first = s.findFirst();
// List<String> names = s.map(String::toUpperCase).toList();
```

**Answer:** No. `findFirst` has already consumed `s`. If you want to create a stream from only the found result, use `first.stream().map(String::toUpperCase).toList()`; if you want to traverse the entire original list, create a new Stream from the list.

## Takeaways

- `findFirst`, `findAny`, `min`, and `max` are terminal operations returning `Optional<T>` because an element might not be found.
- Use **`Optional.map`** when the next step returns a regular value; use **`Optional.flatMap`** when the next step already returns an Optional.
- Use **`Optional.stream()`** (Java 9+) to turn a search result into a Stream of 0 or 1 element, then continue with `filter`, `map`, `flatMap`, or `collect`.
- Use `Stream<Optional<T>>.flatMap(Optional::stream)` to drop empty results when searching multiple IDs; use `flatMapToInt(OptionalInt::stream)` when the data consists of primitive Optionals.
- Do not reuse a Stream after a terminal operation; handle missing data intentionally with `orElse`, `orElseGet`, `or`, or `orElseThrow`, and consider indexing to avoid expensive nested searches.
