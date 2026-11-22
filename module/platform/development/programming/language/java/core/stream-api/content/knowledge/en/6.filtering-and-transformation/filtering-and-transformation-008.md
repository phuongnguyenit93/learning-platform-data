# Handling `null` Elements and `null` Mapping Results

In the Java Stream API, `null` can appear at **two different times**: already present in the data source or produced by a transformation function. For example, a customer list may contain a `null` element; even when every customer is non-`null`, the `email` field returned by `map(Customer::getEmail)` can still be `null`. Without a clearly defined handling policy, a pipeline easily throws `NullPointerException`, produces confusing results, or fails when collecting with a collector.

This lesson belongs to the **Filtering and Transforming Elements** chapter of the **JAVA_STREAM_API** module. The goal is to use `filter`, `map`, `flatMap`, and `collect` safely in lazy pipelines; while also understanding when to use `Optional`, `Stream.ofNullable`, how to handle missing data before grouping, and impacts on performance, state, and parallel processing.

## 1. Does Stream Automatically Remove `null`?

**No.** A `Stream<T>` of reference types can carry `null` elements if its source permits them. `map` can also produce `null` and that element **continues flowing to downstream steps**; `filter` only drops elements when the predicate returns `false`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList("An", null, "Bình");

List<String> cleaned = raw.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());

System.out.println(cleaned); // [An, Bình]
```

`Objects::nonNull` is a method reference for `Objects.nonNull(value)`: it returns `true` if the value is not `null`. It is a `Predicate<T>` compatible with `filter`.

Watch the **data source**: `Arrays.asList("An", null, "Bình")` accepts null elements, whereas factories such as `List.of("An", null)` (Java 9+) throw `NullPointerException` right at list creation. That error occurs while constructing the source, before the pipeline even has a chance to filter.

### 1.1. `null` in the Source vs `null` from `map`

| Where it appears | Example | Risk |
|---|---|---|
| Source element is `null` | `customers` contains a `null` customer | Calling `Customer::getEmail` on that element fails |
| Field inside object is `null` | Customer exists but email is not set | `map(Customer::getEmail)` produces a `null` element |
| Mapping function intentionally returns `null` | `map(code -> lookup.get(code))` when not found | Downstream steps may reject null |
| Element of nested list is `null` | A data group contains a missing entry | `flatMap` does not automatically drop nulls **inside** sub-Streams |

Two commonly used filter steps solve **two separate problems**:

```java
customers.stream()
        .filter(Objects::nonNull)    // protects the Customer object
        .map(Customer::getEmail)     // may return a null String
        .filter(Objects::nonNull);   // protects steps working with email
```

The snippet assumes a `Customer` type with a `getEmail()` getter. A complete example of this type follows in a later section.

## 2. Place `filter` Before Accessing the Element

A common oversight is checking for null **after already calling a method on null**:

```java
List<String> values = Arrays.asList("  Java  ", null, "  Stream  ");

// WRONG: encountering null at map(String::trim) throws NPE.
values.stream()
        .map(String::trim)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

`filter` must come **before** any operation that may dereference the element:

```java
List<String> trimmed = values.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .collect(Collectors.toList());

System.out.println(trimmed); // [Java, Stream]
```

In a pipeline, intermediate operations `filter` and `map` are typically **lazy**: `map(String::trim)` does not execute immediately when declared. The `NullPointerException` in the wrong version usually occurs **when a terminal operation** such as `collect` begins traversing the data. Thus, creating the Stream without error does not mean all transformation steps are safe.

### 2.1. `null` and Empty Strings Are Different Cases

With user input, `""` or a whitespace-only string is not `null`. After removing null, you can continue normalizing:

```java
List<String> source = Arrays.asList(
        null, "  an@example.com  ", "", "   ", "binh@example.com");

List<String> emails = source.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(email -> !email.isEmpty())
        .collect(Collectors.toList());

System.out.println(emails);
// [an@example.com, binh@example.com]
```

`Objects::nonNull` handles **missing references**; `isEmpty` (or `isBlank` from Java 11) handles **strings with empty content**. Only choose operations that match business rules—for instance, a system might want to keep an empty string to indicate the user explicitly cleared a value.

## 3. `map` Returning `null`: Three Handling Policies

`Stream.map` structurally turns each input element into **exactly one output element**, even when the mapping function returns `null`. It does not implicitly convert null into "no result".

Suppose `Customer::getEmail` can return null:

```java
Stream<String> mappedEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail);
// mappedEmails may still contain null elements.
```

Before choosing an API, determine the business meaning of a missing value.

### 3.1. Skip Records Without a Value

```java
List<String> availableEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

This is a clean choice when the goal is simply "get emails that actually exist" and there is no need to preserve positions or a one-to-one correspondence with the original customers.

### 3.2. Replace with a Default Value

```java
List<String> displayEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .map(email -> email == null ? "(chưa có email)" : email)
        .collect(Collectors.toList());
```

This keeps **one result per valid customer**. Pick a default value that makes sense in context; do not use a display string like `"(chưa có email)"` as business data if the system still needs to distinguish a missing value from a real email.

If you want to fail fast on business rules, validate explicitly:

```java
List<String> requiredEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .map(email -> Objects.requireNonNull(
                email, "Email là trường bắt buộc"))
        .collect(Collectors.toList());
```

The error only occurs if a null email exists **and** the terminal operation reaches it.

### 3.3. Keep `null` as-is When Truly Needed

Sometimes output data must preserve element count, including missing positions:

```java
List<String> possiblyNullEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .collect(Collectors.toCollection(java.util.ArrayList::new));
```

Here `ArrayList` is a specific list type that supports null elements. **Keeping null** is an intentional choice: many downstream APIs forbid null. Do not assume every collector or collection accepts null values.

## 4. `Stream.ofNullable`: Turning a Nullable Value into 0 or 1 Element

Since **Java 9**, `Stream.ofNullable(value)` returns:

- A Stream containing **one** element if `value != null`;
- An **empty** Stream if `value == null`.

```java
import java.util.stream.Stream;

System.out.println(Stream.ofNullable("Java").count());        // 1
System.out.println(Stream.ofNullable((String) null).count()); // 0
```

Distinguish this from `Stream.of((String) null)`: that call creates a Stream with **one null element**, not an empty Stream.

```java
long containsNull = Stream.of((String) null).count();      // 1
long skipsNull = Stream.ofNullable((String) null).count(); // 0
```

### 4.1. Dropping `null` Results from `map` Using `flatMap`

`flatMap` takes each element and merges sub-Streams into one unified Stream. Combine it with `Stream.ofNullable` so each value maps to **zero or one** element:

```java
List<String> emails = customers.stream()
        .filter(Objects::nonNull)
        .flatMap(customer ->
                Stream.ofNullable(customer.getEmail()))
        .collect(Collectors.toList());
```

Equivalent in intent to `map(Customer::getEmail).filter(Objects::nonNull)`:

```java
List<String> emails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

**Which should you choose?** For a simple field, `map(...).filter(Objects::nonNull)` is often easier to read. `Stream.ofNullable` is especially useful when already building a `flatMap` pipeline, or when combining optional values with sources that may yield multiple elements.

Note: `Stream.ofNullable` only checks **the argument passed to it**. If `customer` itself is null, `customer.getEmail()` still fails **before** `ofNullable` is called; therefore, filter the object or check null in the lambda.

### 4.2. Nested Lists Containing `null` Groups

```java
List<List<String>> groups = Arrays.asList(
        Arrays.asList("A", null),
        null,
        Arrays.asList("B", "C"));

List<String> labels = groups.stream()
        .filter(Objects::nonNull)   // drop null groups
        .flatMap(List::stream)      // merge elements from each group
        .filter(Objects::nonNull)   // drop null elements inside groups
        .collect(Collectors.toList());

System.out.println(labels); // [A, B, C]
```

Filtering null at the **sublist level** does not replace filtering null at the **element level**. `flatMap` does not drop nulls emitted by sub-Streams. By `flatMap`'s contract, if the mapper function itself returns a **null Stream** it is treated as an empty Stream; however, returning `Stream.empty()` explicitly usually makes intent clearer.

## 5. `Optional` and Potentially Absent Results

`Optional<T>` represents a **present or absent** value. It never holds a null element: `Optional.ofNullable(null)` returns `Optional.empty()`, while `Optional.of(null)` throws `NullPointerException`.

```java
import java.util.Optional;

Optional<String> missing = Optional.ofNullable((String) null);
System.out.println(missing.isPresent()); // false
```

If a mapper returns `Optional<String>`, a plain `map` produces `Stream<Optional<String>>`. Since Java 9, `Optional.stream()` converts each Optional into a 0- or 1-element Stream:

```java
List<String> normalized = customers.stream()
        .filter(Objects::nonNull)
        .flatMap(customer -> Optional.ofNullable(customer.getEmail())
                .map(String::trim)
                .filter(email -> !email.isEmpty())
                .stream())
        .collect(Collectors.toList());
```

`Optional.map` also has a special property: when the mapping function returns null, the result is `Optional.empty()`. That is how **`Optional`** handles null, not the rule of `Stream.map`.

For transforming a single simple field, `Optional` can add unnecessary complexity. It fits well when an API already returns Optional, when there are multiple optional processing steps, or when you want to express potentially missing results explicitly at method boundaries.

### 5.1. `findFirst`/`findAny` Cannot Represent a `null` Result

A subtle trap:

```java
// May throw NPE: the selected element is null.
Stream.of((String) null).findFirst();

// Safe: null values are dropped before searching.
Optional<String> first = Stream.of((String) null, "A")
        .filter(Objects::nonNull)
        .findFirst(); // Optional[A]
```

`findFirst` and `findAny` return `Optional<T>`, which cannot contain null. If the selected element is null, the call may throw `NullPointerException`. Do not assume `Optional` automatically drops all null elements from an input Stream. Filter or normalize before the terminal operation.

## 6. Complete Example: Cleaning Customer Emails

The program below runs on **Java 9 or later** (as it uses `Stream.ofNullable`). It distinguishes null customers, null emails, blank strings, and null regions; it both builds a normalized email list and counts invalid data. Operations work over data that is immutable during traversal.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NullSafeStreamDemo {
    static final class Customer {
        private final String name;
        private final String email;
        private final String region;

        Customer(String name, String email, String region) {
            this.name = name;
            this.email = email;
            this.region = region;
        }

        String getName()   { return name; }
        String getEmail()  { return email; }
        String getRegion() { return region; }
    }

    public static void main(String[] args) {
        List<Customer> customers = Arrays.asList(
                new Customer("An", " AN@EXAMPLE.COM ", "Bắc"),
                null,
                new Customer("Bình", null, "Bắc"),
                new Customer("Chi", "   ", null),
                new Customer("Dũng", " dung@example.com ", "Nam")
        );

        // Drop null customers before calling getters.
        // Then drop null emails before trim/toLowerCase.
        List<String> normalizedEmails = customers.stream()
                .filter(Objects::nonNull)
                .map(Customer::getEmail)
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(email -> !email.isEmpty())
                .map(email -> email.toLowerCase(Locale.ROOT))
                .collect(Collectors.toList());

        System.out.println(normalizedEmails);
        // [an@example.com, dung@example.com]

        // Two real customers exist but lack a valid email.
        long missingEmailCount = customers.stream()
                .filter(Objects::nonNull)
                .filter(customer -> customer.getEmail() == null
                        || customer.getEmail().trim().isEmpty())
                .count();
        System.out.println(missingEmailCount); // 2

        // Extract provided regions using Java 9+.
        List<String> regions = customers.stream()
                .filter(Objects::nonNull)
                .flatMap(customer -> Stream.ofNullable(customer.getRegion()))
                .collect(Collectors.toList());
        System.out.println(regions); // [Bắc, Bắc, Nam]

        // Must filter out null regions before groupingBy.
        Map<String, Long> countsByRegion = customers.stream()
                .filter(Objects::nonNull)
                .filter(customer -> customer.getRegion() != null)
                .collect(Collectors.groupingBy(
                        Customer::getRegion,
                        Collectors.counting()));
        System.out.println(countsByRegion.get("Bắc")); // 2
        System.out.println(countsByRegion.get("Nam")); // 1

        Optional<String> firstValidEmail = customers.stream()
                .filter(Objects::nonNull)
                .flatMap(customer -> Stream.ofNullable(customer.getEmail()))
                .map(String::trim)
                .filter(email -> !email.isEmpty())
                .findFirst();

        System.out.println(firstValidEmail.orElse("(không có)"));
        // AN@EXAMPLE.COM
    }
}
```

Because the input is an ordered `List` and the pipeline runs sequentially, the email order in the example is preserved as it appears in the filtered list. Iteration order over `Map` keys from `groupingBy` is not guaranteed; the example uses key-based `get` to avoid depending on that order.

## 7. `null` in Terminal Operations and Collectors

Not every pipeline endpoint shares the same null contract. Handle nulls **before** passing data to APIs with strict requirements.

| API/processing step | Things to note |
|---|---|
| `collect(Collectors.toList())` | Returns a `List` with no guarantees on type, mutability, or other properties; filter nulls if downstream rejects them |
| `collect(Collectors.toCollection(ArrayList::new))` | Explicitly specifies `ArrayList`; can intentionally retain null elements |
| `collect(Collectors.toUnmodifiableList())` (Java 10+) | Throws `NullPointerException` if any collected value is null |
| `collect(Collectors.toMap(keyMapper, valueMapper))` | Mapped values must not be null; filter/normalize beforehand; keys should also have an explicit non-null contract |
| `collect(Collectors.groupingBy(classifier))` | A classifier returning null throws `NullPointerException`; filter or replace group label beforehand |
| `findFirst()` / `findAny()` | A selected null element can throw `NullPointerException` |
| `mapToInt(Integer::intValue)` | Encountering null fails during unboxing; filter before switching to a primitive stream |
| `sorted()` | Natural ordering usually does not handle null; if sorting nulls is needed, use a suitable Comparator |

### 7.1. `toMap`: Filtering Missing Keys/Values Before Collecting

```java
// Assume Customer::getName() is the key, getEmail() is the value.
Map<String, String> byName = customers.stream()
        .filter(Objects::nonNull)
        .filter(customer -> customer.getName() != null)
        .filter(customer -> customer.getEmail() != null)
        .collect(Collectors.toMap(
                Customer::getName,
                Customer::getEmail));
```

The snippet above also requires **unique keys**; if duplicate names exist, the two-argument `toMap` overload throws `IllegalStateException`. A merge function can be provided for duplicate keys, though handling duplicate keys is a separate requirement from handling null.

### 7.2. `groupingBy`: Deciding Policy for Missing Group Keys

```java
Map<String, Long> counts = customers.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                customer -> customer.getRegion() == null
                        ? "CHƯA_XÁC_ĐỊNH"
                        : customer.getRegion(),
                Collectors.counting()));
```

This approach **keeps customers missing a region** in a dedicated group. If business rules require excluding those customers, use `filter(customer -> customer.getRegion() != null)` before `groupingBy` instead of assigning a default label.

### 7.3. `sorted`: Distinguishing Null Objects from Null Keys

```java
import java.util.Comparator;

// Allow String elements themselves to be null, placing nulls last.
List<String> ordered = Arrays.asList("B", null, "A").stream()
        .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
        .collect(Collectors.toList());
// [A, B, null]

// For non-null Customer whose name may be null:
Comparator<Customer> byNullableName = Comparator.comparing(
        Customer::getName,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

If `Customer` itself can also be null, add an outer null-handling layer such as `Comparator.nullsLast(byNullableName)`; using a null-safe comparator only on the name key does not protect calling the getter on a null Customer.

### 7.4. Unboxing Does Not Automatically Turn `null` into 0

```java
List<Integer> input = Arrays.asList(1, null, 3);

int sum = input.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 4
```

Do not write `mapToInt(Integer::intValue)` directly if the input can be null. Null has no implicit representation in `IntStream`; if you want to treat null as `0`, choose that policy explicitly, such as `mapToInt(value -> value == null ? 0 : value)`.

## 8. Ordering, Laziness, and Parallel Processing

A pipeline containing `filter(Objects::nonNull)` and `map` is typically processed **on demand** by the terminal operation. This allows skipping null objects without creating intermediate lists, yet has three consequences:

1. **Preserves original data**: `filter` produces a stream view of elements; it does not remove null elements from the source `List`.
2. **Do not infer mapper call counts from side effects**: with short-circuiting operations like `findFirst` and optimizations that can elide intermediate operations, logging, incrementing counters, or mutating data inside `map` is not a reliable way to track element counts.
3. **Processing functions should have no shared state**: lambdas relying on mutable variables or modifying the source during traversal easily cause bugs, especially when `parallel()` is enabled.

```java
// Declare a safe pipeline when only non-null names are needed.
List<String> names = customers.parallelStream()
        .filter(Objects::nonNull)
        .map(Customer::getName)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

The example only reads data and shares no external mutable accumulator; the collector coordinates gathering results. However, `parallelStream()` is not automatically faster on small lists because of task-splitting and result-merging overhead. With ordered sources like `List`, `filter` and `map` do not reorder elements on their own, yet `parallelStream().forEach(...)` does not guarantee **action execution** order.

Do not use `peek` to "handle null" by mutating objects in place. `peek` is an observation operation and remains lazy; it is no substitute for explicit filtering or mapping rules.

## 9. Common Mistakes

| Error-prone code | Why it is wrong or misleading | How to handle |
|---|---|---|
| `stream.map(String::trim).filter(Objects::nonNull)` | `trim` already dereferenced null before filtering | Place `filter(Objects::nonNull)` before `map` |
| `customers.map(Customer::getEmail)` when null Customers exist | Calls getter on a null reference | Filter null objects first |
| Thinking `map` returning null disappears automatically | `Stream.map` preserves a null element | Filter after `map` or use `flatMap(Stream::ofNullable)` |
| `Stream.of((String) null)` expecting an empty Stream | This is a one-element Stream containing null | Use `Stream.ofNullable` (Java 9+) |
| `findFirst` on a Stream starting with null | `Optional` cannot represent null | Filter nulls before searching |
| `groupingBy` with a classifier that can return null | A null classifier throws an error | Either drop records or assign a default group key |
| `toMap` with a value mapper returning null | Collecting can throw `NullPointerException` | Filter or normalize values |
| `mapToInt(Integer::intValue)` with null elements | Unboxing null fails | Filter nulls or apply an explicit default rule |
| Using `List.of` with null to build test data | Factory forbids null elements | Use `Arrays.asList` when intentionally testing null |
| Filtering null without checking business requirements | May drop records needing error reporting or positional preservation | Choose explicitly: skip, default, retain, or reject |

## 10. Practice Exercises

### Exercise 1: Filtering and Normalizing Codes

Input:

```java
List<String> codes = Arrays.asList(null, " ab1 ", "", "  ", "CD2");
```

Requirement: drop nulls and blank strings, convert to uppercase. A Java 8 solution:

```java
List<String> result = codes.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(Collectors.toList());
// [AB1, CD2]
```

### Exercise 2: Selecting Values from a Lookup That Can Return `null`

Suppose `Map<String, Integer> prices` holds prices by code and `codes` has missing codes. Build a list of existing prices:

```java
Map<String, Integer> prices = new java.util.HashMap<>();
prices.put("A", 10);
prices.put("B", 20);

List<String> lookupCodes = Arrays.asList("A", "Z", null, "B");

List<Integer> existingPrices = lookupCodes.stream()
        .filter(Objects::nonNull)
        .map(prices::get)            // Z -> null
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
// [10, 20]
```

### Exercise 3: Recognizing the Right Filter Position

With `Arrays.asList(null, "  A  ")`, why is `map(String::trim).filter(Objects::nonNull)` unsafe? Answer: because `String::trim` is called on null when the terminal operation visits the first element; `filter(Objects::nonNull)` must be placed earlier.

### Exercise 4: Preserving Result Count

Source `Arrays.asList("A", null, "C")` needs to output `["A", "CHƯA_CÓ", "C"]`. Should you use `filter(Objects::nonNull)`? No, because that loses the second position. Use:

```java
List<String> labels = Arrays.asList("A", null, "C").stream()
        .map(value -> value == null ? "CHƯA_CÓ" : value)
        .collect(Collectors.toList());
// [A, CHƯA_CÓ, C]
```

### Exercise 5: Designing Groups for Missing Data

If `Customer::getRegion` returns null, is `groupingBy(Customer::getRegion)` appropriate? No; you must choose a policy: drop customers missing a region before grouping, or map null to a group key such as `"CHƯA_XÁC_ĐỊNH"` to count separately. The choice depends on reporting requirements.

## 11. Guidelines for Choosing a Handling Strategy

When designing a pipeline, ask in sequence: **can source elements be null**, **can mapping functions return null**, and **what business meaning does a missing result carry**. Filter with `Objects::nonNull` before any dereferencing operation, then inspect the output of `map` if the mapper can return null. Use `Stream.ofNullable` or `Optional.stream` when modeling an optional value producing **0 or 1 element**. Before `findFirst`, unboxing, `groupingBy`, `toMap`, or collectors rejecting null, normalize data to match the target API's contract. This keeps Stream pipelines declarative and clear while preventing errors deferred until terminal operation execution.
