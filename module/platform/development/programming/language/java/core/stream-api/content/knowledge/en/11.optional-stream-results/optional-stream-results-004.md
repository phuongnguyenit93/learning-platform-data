# Mapping and Filtering Results with map, flatMap, and filter

> **Chapter:** Optional in Stream Results  
> **Module:** JAVA_STREAM_API  
> **Goal:** Learn how to handle potentially absent results from Stream operations using `Optional.map`, `Optional.flatMap`, and `Optional.filter`; build safe processing chains, distinguish Optional from Stream, and control `null`, errors, and default values.

The Java Stream API supports declarative data processing through lazy pipelines with `filter`, `map`, `reduce`, `collect`, and many other operations. Certain terminal operations, such as `findFirst()`, `findAny()`, `min()`, `max()`, and `reduce(BinaryOperator)`, do not guarantee a return value: the Stream may be empty or no element may satisfy the condition. Java uses **`Optional<T>`** to describe a result that may or may not have a value without relying on `null` as the primary signal.

Once you have an `Optional<T>`, you can **map the inner value** with `map`, **chain another lookup that may be absent** with `flatMap`, and **keep the result only if it satisfies a condition** with `filter`. These are the three main operations of this lesson.

This knowledge also helps you use `Optional` properly in grouping, custom collectors, and parallel processing problems in the **JAVA_STREAM_API** module. When the source is supplied by a `Spliterator` or by advanced Stream transformations such as Stream Gatherers, the final result may still be an optional value; handling empty states and resources remains the same.

## 1. Where Does Optional Appear in a Stream Pipeline?

Example finding the first order with an amount of at least 100,000:

```java
import java.util.List;
import java.util.Optional;

record Order(String id, long amount) {}

List<Order> orders = List.of(
    new Order("O-01", 50_000),
    new Order("O-02", 180_000),
    new Order("O-03", 90_000)
);

Optional<Order> found = orders.stream()
    .filter(order -> order.amount() >= 100_000)
    .findFirst();

// found contains Order("O-02", 180000).
```

The first pipeline consists of the source `orders.stream()`, an intermediate operation `Stream.filter(...)`, and the terminal operation `Stream.findFirst()`. **`findFirst()` terminates the Stream and returns `Optional<Order>`**, not `Stream<Order>`.

Then we continue processing the result:

```java
Optional<String> orderId = found
    .map(Order::id)
    .filter(id -> id.startsWith("O-"));

System.out.println(orderId.orElse("Not found")); // O-02
```

This snippet calls **`Optional.map` and `Optional.filter`** on the obtained result, without going back to consume the old Stream.

```text
orders.stream()
      │
      ▼
Stream<Order> ── filter(...) ── findFirst() ──► Optional<Order>
                                                  │
                                                  ▼
                                              map(Order::id)
                                                  │
                                                  ▼
                                             Optional<String>
                                                  │
                                                  ▼
                                            filter(predicate)
                                                  │
                                     ┌────────────┴────────────┐
                                     ▼                         ▼
                             Optional<String>           Optional.empty()
                                has value
```

If there is no valid order, `found` is `Optional.empty()` and the subsequent mapping and predicate functions are not invoked.

## 2. What Is Optional and How Does It Differ From Stream?

`Optional<T>` is an object holding **at most one non-`null` value**. It has two states:

- **Present:** `Optional.of(value)` with `value != null`.
- **Empty:** `Optional.empty()`.

Unlike `Stream<T>`, `Optional<T>` does not represent a multi-element source and **is not a single-use traversal pipeline**. Optional's `map`, `flatMap`, and `filter` methods return a new Optional and operate on at most one value.

| Criterion | `Stream<T>` | `Optional<T>` |
| --- | --- | --- |
| Number of elements representable | 0, 1, or many | 0 or 1 |
| Primary purpose | Processing a sequence of elements | Representing a potentially absent result |
| `map` | Maps each element of the Stream | Maps a single value if present |
| `flatMap` | Maps each element to a Stream and flattens | Maps a value to an Optional and avoids nested Optionals |
| `filter` | Discards elements failing the condition | Keeps the present Optional or returns an empty Optional |
| Laziness | Intermediate operations are usually lazy, requiring a terminal operation | Lambdas of `map`/`flatMap`/`filter` on a present Optional execute when those methods are called |
| Consumed once | Yes, a Stream object can only be consumed once | No, methods on an Optional can be called multiple times |

Example:

```java
Optional<String> name = Optional.of("An");

Optional<String> upper = name.map(String::toUpperCase);
Optional<Integer> length = name.map(String::length);

// upper = Optional[AN]
// length = Optional[2]
// name still holds "An".
```

Even though `name` can be used multiple times, if the inner value is a mutable object, Optional **does not automatically make that object immutable**. Nor should you infer from Optional's reusability that the Stream that produced it can be reused.

### 2.1. Stream Terminal Operations That Typically Return Optional

| Terminal operation | Result type | Why can it be empty? |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | Source has no elements or all were filtered out |
| `findAny()` | `Optional<T>` | No element to select |
| `min(comparator)` | `Optional<T>` | No elements to compare |
| `max(comparator)` | `Optional<T>` | No elements to compare |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | No elements and no identity value provided |
| `IntStream.min()/max()/findFirst()` | `OptionalInt` | No `int` value |
| `LongStream.min()/max()/findFirst()` | `OptionalLong` | No `long` value |
| `DoubleStream.average()` | `OptionalDouble` | Cannot compute average from an empty source |

Conversely, `count()` returns `long` (which can be 0), `IntStream.sum()` returns `int`, and `collect(...)` returns a result according to the collector's contract. These operations do not automatically return `Optional<T>` merely because the input Stream is empty.

## 3. Optional.map: Transforming a Value If Present

Abbreviated signature of `Optional.map`:

```java
<U> Optional<U> map(Function<? super T, ? extends U> mapper);
```

Semantics:

1. If the Optional **has a value**, apply `mapper` to that value.
2. If `mapper` returns a non-`null` value, the result is an `Optional<U>` containing the new value.
3. If `mapper` returns `null`, the result is `Optional.empty()`.
4. If the initial Optional is empty, do not call `mapper` and return an empty result.

### 3.1. Mapping From One Type to Another

```java
Optional<Order> first = orders.stream()
    .filter(order -> order.amount() > 100_000)
    .findFirst();

Optional<Long> amount = first.map(Order::amount);
Optional<String> label = first.map(order ->
    order.id() + " - " + order.amount()
);

// amount = Optional[180000]
// label = Optional[O-02 - 180000]
```

Here `Order::amount` is a method reference equivalent to `order -> order.amount()`. Java uses `Function<Order, Long>` as the target type for `Optional.map`; the `long` value from the record is boxed into `Long`.

Multiple steps can be chained:

```java
Optional<String> normalizedId = first
    .map(Order::id)
    .map(String::trim)
    .map(String::toUpperCase);

// Optional[O-02]
```

Each step processes the value of the preceding Optional. If any step produces an empty Optional, subsequent steps skip their mappers.

### 3.2. Empty Optional Helps Avoid Repetitive Conditional Checks

```java
Optional<String> missing = Optional.<Order>empty()
    .map(Order::id)
    .map(String::trim);

System.out.println(missing.isEmpty()); // true
```

No `NullPointerException` occurs from attempting to call `id()` on a nonexistent order. However, this **does not mean all exceptions are absorbed by Optional**: if the mapper throws an exception, the exception still propagates.

### 3.3. What If the Mapper Returns null?

`Optional.map` uses semantics equivalent to wrapping the mapper's result with `Optional.ofNullable`:

```java
Optional<String> source = Optional.of("An");

Optional<Integer> result = source.map(name -> null);

System.out.println(result.isEmpty()); // true
```

This is useful when integrating legacy APIs that may return `null`. However, it is better to explicitly define at data boundaries that `null` means "no result". If a method is supposed to always return a value yet returns `null` due to a programming bug, mapping it to an empty Optional can mask the real cause.

### 3.4. Stream Laziness vs. Optional Mapper Invocation

Compare:

```java
Stream<String> stream = Stream.of("an")
    .map(value -> {
        System.out.println("Stream map: " + value);
        return value.toUpperCase();
    });

System.out.println("Stream created");
// Stream.map lambda has not necessarily executed yet.

Optional<String> optional = Optional.of("an")
    .map(value -> {
        System.out.println("Optional map: " + value);
        return value.toUpperCase();
    });
// Optional.map lambda has already run during the map call because Optional has a value.

List<String> values = stream.toList();
// Now the Stream is consumed, and the mapper is evaluated as needed.
```

Distinguish the execution timing so you do not confuse the two identically named APIs.

## 4. Optional.flatMap: Chaining an Operation That Also Returns Optional

Abbreviated signature:

```java
<U> Optional<U> flatMap(
    Function<? super T, ? extends Optional<? extends U>> mapper
);
```

`Optional.flatMap` is used when **the function receives the inner value and returns another Optional**. The result is flattened into a single Optional layer.

### 4.1. The Nested Optional Problem

Suppose a customer object has a method returning an optional email:

```java
record Customer(String id, Optional<String> email) {}

Customer customer = new Customer(
    "C-01",
    Optional.of("an@example.com")
);
```

If using `map`:

```java
Optional<Customer> found = Optional.of(customer);

Optional<Optional<String>> nested =
    found.map(Customer::email);
```

`Customer::email` already returns `Optional<String>`. When `map` wraps it, the type becomes `Optional<Optional<String>>`. Every time you retrieve data, you have to handle two layers of presence/absence, which is usually unnecessary.

Using `flatMap`:

```java
Optional<String> flat =
    found.flatMap(Customer::email);

// flat = Optional[an@example.com]
```

This reads directly as: "If the customer is found, proceed to get the email if present".

### 4.2. Example of a Two-Step Dependent Lookup

Suppose a method finds a customer:

```java
static Optional<Customer> findCustomer(
        List<Customer> customers,
        String id
) {
    return customers.stream()
        .filter(customer -> customer.id().equals(id))
        .findFirst();
}
```

From an order containing `customerId`:

```java
record Order(String id, String customerId, long amount) {}

Optional<String> email = orders.stream()
    .filter(order -> order.id().equals("O-01"))
    .findFirst()
    .flatMap(order -> findCustomer(customers, order.customerId()))
    .flatMap(Customer::email);
```

The variables `orders` and `customers` in this example are the corresponding business lists, which will be declared in full in the comprehensive example in section 10. The chain can become empty at each step: order not found, customer not found, or customer has no email yet.

### 4.3. Do Not Use flatMap for Functions Returning Regular Values

If you want to get the customer's name:

```java
record Customer(String id, String name, Optional<String> email) {}

Optional<Customer> found = Optional.of(
    new Customer("C-01", "An", Optional.of("an@example.com"))
);

Optional<String> name = found.map(Customer::name);
Optional<String> email = found.flatMap(Customer::email);
```

- `Customer::name` returns `String` → use `map`.
- `Customer::email` returns `Optional<String>` → use `flatMap`.

**Selection rule by signature:**

| Function to call | Choose | Result type |
| --- | --- | --- |
| `T -> U` | `optional.map(...)` | `Optional<U>` |
| `T -> Optional<U>` | `optional.flatMap(...)` | `Optional<U>` |
| `T -> boolean` | `optional.filter(...)` | `Optional<T>` |

### 4.4. flatMap Does Not Accept null From the Mapper

Unlike `map`, `flatMap` **requires the mapper to return a non-null Optional object**. If the mapper returns `null`, Java throws `NullPointerException`:

```java
Optional<String> value = Optional.of("x");

// Throws NullPointerException:
// Optional<String> result = value.flatMap(x -> null);
```

If a legacy API returns `String` or `null`, wrap it with `Optional.ofNullable`:

```java
static String legacyLookup(String key) {
    return key.equals("ok") ? "Found" : null;
}

Optional<String> found = Optional.of("missing")
    .flatMap(key -> Optional.ofNullable(legacyLookup(key)));

System.out.println(found.isEmpty()); // true
```

The `legacyLookup` method in the example is a standalone method that can be placed in a Java class. Do not use `Optional.of(legacyLookup(...))` if the result can be `null`, because `Optional.of(null)` throws `NullPointerException`.

### 4.5. Behavior When the Source Optional Is Empty

```java
Optional<String> absent = Optional.<Customer>empty()
    .flatMap(Customer::email);

System.out.println(absent); // Optional.empty
```

The call to `Customer::email` does not occur. Therefore, processing chains depending on multiple lookups can be expressed without manual `isPresent()` checks at every step.

## 5. Optional.filter: Keeping Only Results Matching a Condition

Signature:

```java
Optional<T> filter(Predicate<? super T> predicate);
```

`Optional.filter` does not change the data type:

- If the Optional is empty, return an empty Optional and **do not call the predicate**.
- If a value is present and the predicate returns `true`, keep the value as is.
- If a value is present and the predicate returns `false`, return an empty Optional.
- If the predicate throws an exception, the exception is propagated outward.

### 5.1. Checking a Search Result

```java
Optional<Order> candidate = orders.stream()
    .filter(order -> order.id().equals("O-02"))
    .findFirst();

Optional<Order> approved = candidate
    .filter(order -> order.amount() >= 100_000);
```

There are three possibilities: no order matches the ID; the order exists but its amount does not meet the threshold; or the order meets the condition. The first two cases both produce `Optional.empty()`. If business logic needs to **distinguish "does not exist" from "exists but does not qualify"**, do not use an empty Optional as the sole state; use a result type that describes the reason, such as an enum or sealed result.

### 5.2. Filter After map or Before map?

Suppose we need to find a customer who has a non-empty email:

```java
Optional<String> email = foundCustomer
    .flatMap(Customer::email)
    .map(String::trim)
    .filter(text -> !text.isEmpty());
```

Here `filter` receives `String` because `flatMap` and `map` produced `Optional<String>`. If checking the customer object first:

```java
Optional<String> email = foundCustomer
    .filter(customer -> customer.active())
    .flatMap(Customer::email);
```

Then `filter` receives `Customer`. The snippet assumes the `Customer` type has an `active()` method; see the full illustration in section 10.

**The order of operations expresses business rules.** Filtering by customer status before retrieving the email differs from checking only the email content.

### 5.3. Do Not Turn filter Into Exception Handling

`filter` should only check a condition. Example:

```java
Optional<String> valid = Optional.of("42")
    .filter(text -> text.chars().allMatch(Character::isDigit));
```

If converting a string to a number, `map(Integer::parseInt)` can throw `NumberFormatException` when the data is invalid. Optional does not automatically turn that exception into empty; you must define an input validation strategy or separate error handling.

### 5.4. Comparing Stream.filter and Optional.filter

```java
List<Integer> results = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .toList(); // [2, 4]

Optional<Integer> result = Optional.of(3)
    .filter(n -> n % 2 == 0); // Optional.empty
```

`Stream.filter` can keep multiple elements; `Optional.filter` only keeps or discards a single present value. Both methods share the same `Predicate<T>` condition shape, but differ in element count and execution lifecycle.

## 6. Combining map, flatMap, and filter in a Single Chain

Suppose given an order ID, we need the email domain of an active customer with a minimally valid email:

```java
Optional<String> domain = findOrder(orderId)
    .filter(Order::paid)
    .flatMap(order -> findCustomer(order.customerId()))
    .filter(Customer::active)
    .flatMap(Customer::email)
    .map(String::trim)
    .filter(text -> text.contains("@"))
    .map(text -> text.substring(text.indexOf('@') + 1))
    .filter(text -> !text.isBlank());
```

Here `findOrder` and `findCustomer` are business methods returning `Optional`; `Order` has `paid()`, `Customer` has `active()`, and `email()` returns `Optional<String>`. The snippet illustrates the shape of the pipeline; full definitions of the types are presented in section 10.

Type flow:

```text
Optional<Order>
   │ filter(Order::paid)
   ▼
Optional<Order>
   │ flatMap(order -> findCustomer(...))
   ▼
Optional<Customer>
   │ filter(Customer::active)
   ▼
Optional<Customer>
   │ flatMap(Customer::email)
   ▼
Optional<String>
   │ map(String::trim)
   ▼
Optional<String>
   │ filter(text -> text.contains("@"))
   ▼
Optional<String>
   │ map(extractDomain)
   ▼
Optional<String>
   │ filter(text -> !text.isBlank())
   ▼
Optional<String>
```

No step calls `get()`. When a link is missing, subsequent steps automatically skip value processing.

**Note:** checking `contains("@")` is only a simple illustration, **not a complete email address validator**. In real business logic, validation and normalization policies must match system requirements.

## 7. How to Handle the Final Optional Result

The three operations `map`, `flatMap`, and `filter` still return an Optional. When you need to return data to the caller or display the result, choose a policy for the empty state.

### 7.1. orElse: Eagerly Evaluated Replacement Value

```java
String label = Optional.of("An")
    .map(String::toUpperCase)
    .orElse("No name"); // AN
```

`orElse(other)` always takes **an already-evaluated value**. If the expression creating the default value is expensive, it is still evaluated before `orElse` is called:

```java
static String expensiveFallback() {
    System.out.println("Creating fallback");
    return "Default";
}

String name = Optional.of("An")
    .orElse(expensiveFallback());

// Prints "Creating fallback" even though Optional already has "An".
```

### 7.2. orElseGet: Calls Supplier Only When Empty

```java
String name = Optional.of("An")
    .orElseGet(() -> expensiveFallback());

// Does not call expensiveFallback() because Optional has a value.
```

Same resulting value, but `orElseGet` is appropriate when creating the replacement value is costly or has side effects. When the default value is just a constant like `"N/A"`, `orElse` is usually simpler.

### 7.3. orElseThrow: Empty State Is an Error

```java
Order required = orders.stream()
    .filter(order -> order.id().equals("O-02"))
    .findFirst()
    .orElseThrow(() ->
        new IllegalArgumentException("Order not found")
    );
```

Use `orElseThrow` when **the business contract truly requires data to be present**. Do not arbitrarily turn a valid nonexistent result into an error.

### 7.4. ifPresent and ifPresentOrElse: Actions at the System Boundary

```java
Optional<String> name = Optional.of("An");

name.ifPresent(System.out::println);

name.ifPresentOrElse(
    System.out::println,
    () -> System.out.println("No name")
); // Java 9+
```

`ifPresent` and `ifPresentOrElse` return `void`. They are suitable for final actions like displaying or updating an external component when an effect is desired. If you need to continue **transforming and passing the result**, keeping the Optional through `map`, `flatMap`, and `filter` is clearer.

### 7.5. Why Not Overuse get?

`Optional.get()` throws `NoSuchElementException` if empty. This pattern tends to produce verbose code and missed handling:

```java
// Verbose and error-prone during maintenance:
if (maybeName.isPresent()) {
    String upper = maybeName.get().toUpperCase();
}
```

When the goal is transforming the value, use:

```java
Optional<String> upper = maybeName.map(String::toUpperCase);
```

If the result must exist, use `orElseThrow` with an appropriate message and exception type. The goal of Optional is to force code authors to think about the absent case, rather than merely shifting the risk of failure to another `get()` call.

## 8. Optional.stream: Bringing Present/Absent Results Back Into a Stream Pipeline

Since Java 9, `Optional<T>` has the method:

```java
Stream<T> stream();
```

This method returns:

- A **one-element** Stream if the Optional has a value.
- An **empty** Stream if the Optional has no value.

Example:

```java
List<String> present = Optional.of("Java")
    .stream()
    .toList(); // [Java]

List<String> missing = Optional.<String>empty()
    .stream()
    .toList(); // []
```

### 8.1. Turning a Stream<Optional<T>> Into a Stream<T>

A practical scenario is multiple independent lookups, each returning an Optional:

```java
List<Optional<String>> emailLookups = List.of(
    Optional.of("an@example.com"),
    Optional.empty(),
    Optional.of("chi@example.com")
);

List<String> emails = emailLookups.stream()
    .flatMap(Optional::stream)
    .toList();

// [an@example.com, chi@example.com]
```

If you only use `map(optional -> optional.orElse(null))`, the list can contain `null`, making subsequent steps prone to errors and losing the present/absent semantics. `flatMap(Optional::stream)` keeps exactly the present values.

### 8.2. Combining an Input List With a Function Returning Optional

```java
static Optional<Integer> parsePositiveInt(String raw) {
    try {
        int value = Integer.parseInt(raw);
        return value > 0 ? Optional.of(value) : Optional.empty();
    } catch (NumberFormatException e) {
        return Optional.empty();
    }
}

List<Integer> values = Stream.of("12", "x", "-3", "7")
    .map(OptionalLesson::parsePositiveInt)
    .flatMap(Optional::stream)
    .toList();

// [12, 7]
```

`OptionalLesson` is an illustrative class name containing `parsePositiveInt`. This example intentionally chooses the policy "skip invalid strings"; if the application needs to report the exact invalid line, use a dedicated result type containing success/failure details instead of turning all errors into an empty Optional.

This can be written concisely:

```java
List<Integer> values = Stream.of("12", "x", "-3", "7")
    .flatMap(text -> parsePositiveInt(text).stream())
    .toList();
```

Note that **`Stream.flatMap` accepts a function returning a Stream**, whereas **`Optional.flatMap` accepts a function returning an Optional**. `Optional.stream()` is the bridge that lets the two systems work together.

### 8.3. Feeding Multiple Independent Search Results Into Further Processing

```java
Stream<Optional<Order>> searchResults = Stream.of(
    orders.stream().filter(order -> order.id().equals("O-01")).findFirst(),
    orders.stream().filter(order -> order.id().equals("O-99")).findFirst()
);

long foundCount = searchResults
    .flatMap(Optional::stream)
    .count(); // 1, if only O-01 exists.
```

Each `findFirst()` here consumes **a separate Stream** created from `orders`. Each `Optional` already holds a result, while `searchResults` is a Stream containing those two Optionals.

## 9. Optional<T> and Optionals for Primitive Numbers

Terminal operations of primitive streams may return:

- `OptionalInt` for `IntStream.findFirst()`, `min()`, `max()`, or `reduce(...)` without identity.
- `OptionalLong` for the corresponding operations on `LongStream`.
- `OptionalDouble` for the corresponding operations on `DoubleStream`, as well as `average()` of all three primitive streams.

`OptionalInt`, `OptionalLong`, and `OptionalDouble` **do not provide the same full set of `map`, `flatMap`, and `filter` methods as `Optional<T>`**. Thus the following code is invalid:

```java
OptionalInt score = IntStream.of(7, 9).max();

// No OptionalInt.map(...) API like Optional<T>:
// score.map(n -> n * 2);
```

### 9.1. Handle the Numeric Result Directly If Only the Value Is Needed

```java
OptionalInt max = IntStream.of(7, 9, 6).max();

int value = max.orElse(0); // 9
System.out.println(value);
```

If there is no data, `orElse(0)` uses the application-chosen default policy of 0. Do not equate "no score" with "score equals 0" if the system needs to distinguish the two cases.

### 9.2. Switch to an Object Stream When You Need map and Want Optional<T>

Primitive Optionals have `stream()` from Java 9. You can convert the result to an object stream and call `findFirst()`:

```java
Optional<String> label = IntStream.of(7, 9, 6)
    .max()               // OptionalInt
    .stream()            // IntStream with 0 or 1 value
    .mapToObj(n -> "Highest score: " + n)
    .findFirst();        // Optional<String>

// Optional[Highest score: 9]
```

`mapToObj` here runs on the `IntStream` created by `OptionalInt.stream()`, not as a method of `OptionalInt`. This is an intentional conversion path when the required result is `Optional<String>`.

### 9.3. Numeric Types Do Not Automatically Have null Rules

With `IntStream`, elements are `int` and cannot be `null`. When a result is missing, that state lives in `OptionalInt.empty()`. If a common interface requiring `Optional<Integer>` is needed, you can convert in a controlled manner:

```java
OptionalInt primitive = IntStream.of(4, 8).max();

Optional<Integer> boxed = primitive.isPresent()
    ? Optional.of(primitive.getAsInt())
    : Optional.empty();

// boxed = Optional[8]
```

This is a case where `getAsInt()` is acceptable because `isPresent()` was checked within the same expression. When working primarily with numbers, continuing to use `OptionalInt` and the specialized APIs avoids unnecessary boxing.

## 10. Complete Java Example: Resolving Contact Email for an Order

Problem: a system has lists of orders and customers. Return an email only when all conditions hold: the order exists, is paid, meets the minimum amount, the customer exists and is active, and has a non-blank email. Normalize the resulting email using `strip()` and lowercase it with `Locale.ROOT`.

Standalone example running on Java 17+, saved to `OptionalPipelineDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class OptionalPipelineDemo {
    record Customer(
        String id,
        String name,
        boolean active,
        Optional<String> email
    ) {}

    record Order(
        String id,
        String customerId,
        long total,
        boolean paid
    ) {}

    static Optional<Customer> findCustomer(
            List<Customer> customers,
            String id
    ) {
        return customers.stream()
            .filter(customer -> customer.id().equals(id))
            .findFirst();
    }

    static Optional<String> normalizeEmail(Customer customer) {
        return customer.email()
            .map(String::strip)
            .filter(email -> !email.isBlank())
            .map(email -> email.toLowerCase(Locale.ROOT));
    }

    static Optional<String> emailForOrder(
            List<Order> orders,
            List<Customer> customers,
            String orderId
    ) {
        return orders.stream()
            .filter(order -> order.id().equals(orderId))
            .findFirst()
            .filter(Order::paid)
            .filter(order -> order.total() >= 100_000)
            .flatMap(order -> findCustomer(customers, order.customerId()))
            .filter(Customer::active)
            .flatMap(OptionalPipelineDemo::normalizeEmail);
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
            new Customer("C-01", "An", true,
                Optional.of("  AN@Example.com  ")),
            new Customer("C-02", "Bình", true,
                Optional.empty()),
            new Customer("C-03", "Chi", false,
                Optional.of("chi@example.com")),
            new Customer("C-04", "Dung", true,
                Optional.of("   "))
        );

        List<Order> orders = List.of(
            new Order("O-01", "C-01", 150_000, true),
            new Order("O-02", "C-02", 200_000, true),
            new Order("O-03", "C-03", 220_000, true),
            new Order("O-04", "C-01", 90_000, true),
            new Order("O-05", "C-01", 300_000, false),
            new Order("O-06", "C-04", 250_000, true),
            new Order("O-07", "C-99", 250_000, true)
        );

        System.out.println(emailForOrder(
            orders, customers, "O-01"
        ).orElse("No valid email"));
        // an@example.com

        System.out.println(emailForOrder(
            orders, customers, "O-02"
        ).orElse("No valid email"));
        // No valid email

        System.out.println(emailForOrder(
            orders, customers, "O-99"
        ).orElse("No valid email"));
        // No valid email

        List<String> contactEmails = orders.stream()
            .filter(Order::paid)
            .filter(order -> order.total() >= 100_000)
            .map(order -> findCustomer(customers, order.customerId())
                .filter(Customer::active)
                .flatMap(OptionalPipelineDemo::normalizeEmail))
            .flatMap(Optional::stream)
            .distinct()
            .toList();

        System.out.println(contactEmails);
        // [an@example.com]
    }
}
```

### 10.1. Analysis by Return Type

| Code in example | Result type | Role |
| --- | --- | --- |
| `orders.stream().filter(...).findFirst()` | `Optional<Order>` | Order may not exist |
| `.filter(Order::paid)` | `Optional<Order>` | Discard unpaid orders |
| `.filter(order -> order.total() >= 100_000)` | `Optional<Order>` | Discard orders below threshold |
| `.flatMap(order -> findCustomer(...))` | `Optional<Customer>` | Look up customer; avoid `Optional<Optional<Customer>>` |
| `.filter(Customer::active)` | `Optional<Customer>` | Keep only active customers |
| `.flatMap(OptionalPipelineDemo::normalizeEmail)` | `Optional<String>` | Get potentially absent email |
| `.map(String::strip)` | `Optional<String>` | Normalize email if present |
| `.filter(email -> !email.isBlank())` | `Optional<String>` | Discard blank emails |
| `.flatMap(Optional::stream)` on `Stream<Optional<String>>` | `Stream<String>` | Discard empty Optionals in lookup list |

`O-01` has a valid email. `O-02` has no email, `O-03` has an inactive customer, `O-04` is below the threshold, `O-05` is unpaid, `O-06` contains a blank email, and `O-07` points to a nonexistent customer. All non-qualifying cases are represented by `Optional.empty()`.

### 10.2. Intentional Limitations of the Example

- The `normalizeEmail` function only trims leading/trailing whitespace, rejects blank strings, and converts to lowercase. It **does not validate full email syntax**. In real systems, lowercasing the entire email may not suit every address policy; choose normalization rules according to system requirements.
- `findCustomer` traverses the list on every call; on large datasets with many orders and customers, consider indexing customers by `Map<String, Customer>` to avoid repeated linear scans.
- Returning `Optional.empty()` for multiple different reasons simplifies the example. If you need to know the failure reason for user reporting or auditing, design a result type holding an explicit status/error.

## 11. Combining Optional With Grouping and Collectors

For statistical tasks, you can find the largest element within each group:

```java
record Product(String category, String name, long price) {}

List<Product> products = List.of(
    new Product("Books", "Java", 200),
    new Product("Books", "SQL", 150),
    new Product("Equipment", "Mouse", 300)
);

Map<String, Optional<Product>> mostExpensive = products.stream()
    .collect(Collectors.groupingBy(
        Product::category,
        Collectors.maxBy(
            Comparator.comparingLong(Product::price)
        )
    ));
```

The example requires importing `java.util.Map`, `java.util.Comparator`, and `java.util.stream.Collectors`.

`Collectors.maxBy(...)` is a collector returning `Optional<Product>` for each group according to the collector contract. For a synthetically empty group during aggregation or when receiving data from an API that may lack entries, Optional expresses the possibility of having no suitable element; groups created by `groupingBy` from ordinary input elements have at least one element.

After retrieving the `Optional<Product>` for the "Books" group, you can map it:

```java
Optional<String> name = mostExpensive
    .getOrDefault("Books", Optional.empty())
    .map(Product::name);

System.out.println(name.orElse("No product")); // Java
```

If you need to collect the names of the most expensive products across all groups:

```java
List<String> names = mostExpensive.values().stream()
    .flatMap(Optional::stream)
    .map(Product::name)
    .sorted()
    .toList();

// [Java, Mouse] in Java's natural string order.
```

Note: `Map.getOrDefault` differs from `Optional.orElse`; the first handles missing keys in the Map, while the second handles the empty state of an Optional.

### 11.1. Optional and collect Do Not Replace Each Other

A common misunderstanding is using Optional to accumulate multiple elements. Optional only holds 0 or 1 value. If you need to collect multiple orders, use `collect` or `toList` on the Stream. When the result after a terminal operation may be absent, use Optional to continue mapping/filtering.

Example total amount from multiple orders:

```java
long total = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::total)
    .sum(); // long, not Optional<Long>
```

If business logic wants to distinguish "no matching orders" from "total equals 0", you can use `reduce(Long::sum)` on `LongStream` to get `OptionalLong`, or an aggregate type containing both count and total amount.

## 12. Null, Exceptions, and Side Effects

### 12.1. Creating Optional Properly From a Potentially null Source

```java
String legacyEmail = null;

Optional<String> safe = Optional.ofNullable(legacyEmail);
Optional<String> empty = Optional.empty();

// Throws NullPointerException:
// Optional<String> broken = Optional.of(legacyEmail);
```

- `Optional.of(value)` is for values **guaranteed to be non-null**.
- `Optional.ofNullable(value)` converts `null` into `Optional.empty()`.
- `Optional.empty()` represents the absent-value state.

Do not store `null` in a variable declared as `Optional<String>`, because the Optional object itself is then missing, and calls to `map`/`flatMap` will fail:

```java
Optional<String> maybe = null; // Avoid this design.
// maybe.map(String::trim);    // NullPointerException
```

A function declared to return `Optional<T>` should return a real Optional, even if empty.

### 12.2. Optional Does Not Replace Error Management

```java
Optional<Integer> number = Optional.of("abc")
    .map(Integer::parseInt); // NumberFormatException
```

If the data is malformed, `map` does not catch exceptions or automatically turn them into empty.

Use explicit handling if parsing failures are allowed to mean "no valid value":

```java
static Optional<Integer> tryParseInt(String text) {
    try {
        return Optional.of(Integer.parseInt(text));
    } catch (NumberFormatException e) {
        return Optional.empty();
    }
}

Optional<Integer> value = Optional.of("abc")
    .flatMap(OptionalLesson::tryParseInt);
```

`OptionalLesson` is a hypothetical class name containing `tryParseInt`. If you need to display the exact cause of an error, an empty Optional is usually insufficient: use a result type carrying error information or an appropriate exception mechanism.

### 12.3. Do Not Turn map and filter Into Side-Effect Containers

Do not rely on `map` or `filter` to write external state as part of a business requirement:

```java
List<String> audited = new ArrayList<>();

Optional<String> email = foundCustomer
    .flatMap(Customer::email)
    .map(value -> {
        audited.add(value); // Side effect should be separated clearly.
        return value;
    });
```

The snippet uses a hypothetical mutable `audited` list; `ArrayList` is in `java.util`. In small examples, the operation may run; yet the flow becomes coupled to external state, and combining it with parallel Streams or changing execution timing requirements makes maintenance difficult.

If you only need to observe the final result, use `ifPresent`. If mandatory auditing is required, design an explicit business step and define the policy for missing data. In particular, functions inside `Stream.map`/`filter` may be skipped due to lazy evaluation, short-circuiting, or Stream optimizations; do not place mandatory updates there.

## 13. Performance and Data Source Lifecycle

`Optional.map`, `flatMap`, and `filter` process at most one value and usually have minimal cost. In most cases, the major cost lies in **how the initial value is found**:

```java
Optional<Customer> customer = customers.stream()
    .filter(c -> c.id().equals(targetId))
    .findFirst();
```

Calling `findFirst` may traverse part of the list or the entire list if no customer matches. When applied inside a loop over many orders, scanning the same list repeatedly can incur significant cost. For repeated lookups, consider a `Map` keyed by ID, an indexed database, or an appropriate data source design.

### 13.1. Early Termination in Stream Differs From an Already-Resolved Optional

`Stream.findFirst` and `Stream.findAny` can stop early once an element is found. Thus:

```java
Optional<String> firstName = customers.stream()
    .filter(Customer::active)
    .findFirst()
    .map(Customer::name);
```

The Stream may only process up to the first active customer. Afterward, `Optional.map` applies to at most one found result; it does not trigger further source traversal.

In a parallel Stream, `findAny` may select any element and results between runs may differ; `findFirst` respects *encounter order* if the source is ordered. If the business rule needs "the first customer chronologically", ensure source ordering or sort explicitly before searching.

### 13.2. Optional Does Not Automatically Close Stream Resources

When searching in a file or an I/O Stream, close the source properly:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

class FindFirstNonBlankLine {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes.txt");

        Optional<String> firstNonBlank;
        try (Stream<String> lines = Files.lines(path)) {
            firstNonBlank = lines
                .map(String::trim)
                .filter(text -> !text.isEmpty())
                .findFirst();
        }

        String upper = firstNonBlank
            .map(String::toUpperCase)
            .orElse("NO LINE");

        System.out.println(upper);
    }
}
```

The example assumes `notes.txt` exists. `Files.lines` holds an underlying resource that must be closed; `findFirst()` does not close the Stream automatically. After the `try-with-resources` block, the Optional holds an already-extracted `String`, which can be processed further without keeping the file open.

If the value stored inside the Optional is itself an object holding resources, managing that object's lifecycle remains the application's responsibility.

### 13.3. Do Not Create Optional Just to Avoid Every Control Branch

Optional is useful when a result can genuinely be absent. If a method always has a value, returning type `T` directly is clearer. For multi-branch actions or when needing to distinguish multiple failure causes, an explicit control structure or a dedicated result type may fit better than an overly long Optional chain.

## 14. Common Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| `optional.map(x -> findSomething(x))` when `findSomething` returns `Optional<U>` | Creates `Optional<Optional<U>>`. | Use `flatMap`. |
| `optional.flatMap(x -> x.getName())` when `getName` returns `String` | Type mismatch: `flatMap` expects `Optional`. | Use `map`. |
| `optional.flatMap(x -> null)` | `NullPointerException`. | Return `Optional.empty()` or `Optional.ofNullable(...)`. |
| Calling `Optional.of(null)` | `NullPointerException` upon creation. | Use `ofNullable` when null is valid. |
| Thinking `Optional.map` always defers lambdas until a terminal operation | Optional has no terminal pipeline like Stream. | Understand that the mapper runs immediately if the Optional has a value. |
| Writing `optional.get()` without handling empty | `NoSuchElementException`. | `map`, `flatMap`, `filter`, `orElseGet`, or `orElseThrow`. |
| Using `orElse(expensiveFallback())` expecting to skip fallback when present | Fallback is still evaluated before the call. | `orElseGet(() -> expensiveFallback())`. |
| Thinking `Optional.filter` returns a boolean | Returns `Optional<T>`. | Use `isPresent()` to query the final state if a boolean is needed. |
| Expecting `map(Integer::parseInt)` to swallow errors | `NumberFormatException` still propagates. | Validate input or convert errors under a clear policy. |
| Calling `OptionalInt.map` like `Optional<T>.map` | Primitive Optional does not provide that API. | Use `stream().mapToObj(...).findFirst()` or handle the number directly. |
| Using `Stream.flatMap` with a mapper returning Optional | Type mismatch; Stream requires a mapper returning Stream. | `flatMap(x -> maybeValue(x).stream())`. |
| Assuming Optional.empty explains the failure reason | Loses distinction among multiple failure cases. | Use an informative result type when business logic needs it. |
| Mutating external state in pipeline lambdas and relying on call order | Lazy/parallel/short-circuit execution can change behavior. | Separate side effects into explicit business steps. |
| Thinking `findFirst` automatically closes a file | Source resource leak. | `try-with-resources`. |

## 15. Self-Practice Exercises

**Exercise 1 — Getting a record ID.** Given `Stream<Product>` and the condition `price > 100_000`. Use `findFirst` to get `Optional<Product>`, then `map(Product::id)` to get `Optional<String>`. Test with an empty source.

**Exercise 2 — Two lookups.** Given `Optional<Order>` with `customerId`, and a `findCustomer(String)` function returning `Optional<Customer>`. Compare return types when using `map` versus `flatMap`. Turn it into a chain resulting in `Optional<String>` containing the name.

**Exercise 3 — Condition after mapping.** Given `Optional<String>` with value `"  Java  "`. Use `map(String::trim)` then `filter(text -> text.length() >= 4)`, followed by `orElse("Not qualified")`. Test with a blank string or `Optional.empty`.

**Exercise 4 — List of Optionals.** Given `List<Optional<Integer>>` containing three present Optionals and two empty Optionals. Use `stream().flatMap(Optional::stream)` to collect a `List<Integer>` containing only the present numbers.

**Exercise 5 — Expensive default value.** Write a default-creation function with logging. Compare the number of invocations when using `orElse(expensive())` and `orElseGet(() -> expensive())` on an Optional that already has a value.

**Exercise 6 — Result from a primitive stream.** Use `IntStream.of(4, 7, 2).max()`. Convert `OptionalInt` to `Optional<String>` describing the largest value via `stream().mapToObj(...).findFirst()`. Test with `IntStream.empty()`.

**Exercise 7 — Invalid reason.** An order may not exist, be unpaid, or fail to meet a threshold. Try writing `Optional<Order>` with `filter`. Then propose a result type that distinguishes all three states and explain when to use it instead of Optional.

**Exercise 8 — Source requiring closing.** Read lines from a file with `Files.lines`, get the first non-empty line with `findFirst`, and normalize it with `Optional.map` after closing the file. Determine where to place `try-with-resources`.

Hint for Exercise 4:

```java
List<Integer> present = optionals.stream()
    .flatMap(Optional::stream)
    .toList();
```

In this snippet, `optionals` is assumed to be a declared `List<Optional<Integer>>`. If the list contains `null` references themselves instead of `Optional.empty()`, sanitize the input data because `Optional::stream` cannot be invoked on `null`.

## 16. Core Takeaways

- **`Optional<T>`** represents a potentially absent result, typically obtained from `findFirst`, `findAny`, `min`, `max`, or `reduce` without identity; it is not a multi-element Stream.
- **`Optional.map`** is for `T -> U` functions; if a value is present, it applies the mapper and wraps the result in an Optional. A mapper returning `null` yields an empty result.
- **`Optional.flatMap`** is for `T -> Optional<U>` functions; it avoids producing `Optional<Optional<U>>`. The mapper of `flatMap` must return a non-null Optional object.
- **`Optional.filter`** tests a `Predicate<T>` if a value is present; if the condition is false, it returns `Optional.empty()`, while the inner value's type stays unchanged.
- **`map`, `flatMap`, and `filter` on Optional are not lazy like a Stream pipeline.** They process at most one value when called; if the Optional is empty, the behavior function is not invoked.
- **`Optional.stream()` (Java 9+)** is a convenient bridge to flatten `Stream<Optional<T>>` via `flatMap(Optional::stream)`.
- **`orElse`, `orElseGet`, `orElseThrow`, and `ifPresent`** express the policy for the final result; distinguish the eager evaluation of `orElse` from the on-demand evaluation of `orElseGet`.
- **`OptionalInt`, `OptionalLong`, and `OptionalDouble`** are specialized types with APIs different from `Optional<T>`; you can use `stream()` and `mapToObj` when needing to convert to object types.
- **Optional does not catch exceptions automatically, does not manage resources automatically, and does not explain multiple failure reasons.** Choose the right result type, error-handling rules, lookup strategy, and source lifecycle for the problem.
- When combining with lazy pipelines, grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers in **JAVA_STREAM_API**, maintain a clear boundary between a **multi-element stream** and a **single optional result**.
