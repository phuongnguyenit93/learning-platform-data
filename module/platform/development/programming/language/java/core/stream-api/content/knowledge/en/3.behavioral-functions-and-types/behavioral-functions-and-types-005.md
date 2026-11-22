# Combining Predicate and Function to Express Processing Rules

In the Java Stream API, a business requirement often has two parts: **deciding which data is accepted** and **transforming the accepted data into the desired output**. `Predicate<T>` expresses a yes/no condition; `Function<T, R>` expresses a transformation from type `T` to type `R`. When combined, they form small, named, reusable, and easily testable rules.

This lesson belongs to the **Behavioral Functions and Types** section of the **JAVA_STREAM_API** module. The knowledge here is foundational for building `filter`, `map`, `reduce`, and `collect` pipelines; later it can be applied to `groupingBy`, custom collectors, and advanced Stream operations. The focus of this lesson is **writing and combining processing rules with clear types**, while understanding evaluation order, laziness, and state boundaries.

## 1. Distinguishing the Roles of Predicate and Function

Both are *functional interfaces* in `java.util.function`: interfaces with a single abstract method that can be represented with lambdas or method references.

| Aspect | `Predicate<T>` | `Function<T, R>` |
| --- | --- | --- |
| Question answered | "Does this element satisfy the condition?" | "What value does this element transform into?" |
| Abstract method | `boolean test(T value)` | `R apply(T value)` |
| Result | `boolean` | A value of type `R` |
| Common usage | `Stream.filter(predicate)` | `Stream.map(function)` |
| Built-in combinators | `and`, `or`, `negate` | `andThen`, `compose`, `identity` |
| Purpose | Selecting/validating data | Transforming/normalizing data |

String example:

```java
import java.util.function.Function;
import java.util.function.Predicate;

Predicate<String> notBlank = text -> text != null && !text.isBlank();
Function<String, Integer> countCharacters = String::length;

System.out.println(notBlank.test("Java"));          // true
System.out.println(notBlank.test("   "));            // false
System.out.println(countCharacters.apply("Java"));  // 4
```

`Predicate<String>` does not return a modified string, and `Function<String, Integer>` is not a condition check. These two roles differ even if a `Function` is declared with a `Boolean` return type; the natural way to express a conditional rule remains `Predicate`.

In a Stream:

```java
List<String> lengthsAsText = List.of(" Java ", "", "Stream")
    .stream()
    .filter(text -> !text.isBlank())  // Predicate<String>
    .map(String::strip)                // Function<String, String>
    .map(String::length)               // Function<String, Integer>
    .map(String::valueOf)              // Function<Integer, String>
    .toList();

System.out.println(lengthsAsText); // [4, 6]
```

Note: this snippet requires `import java.util.List;`, and snippets in subsequent sections can share imports if placed inside one Java class.

## 2. Combining Multiple Predicates into One Business Rule

A real-world rule often consists of multiple conditions. Instead of cramming everything into one long lambda, name each condition and compose them.

Three key methods:

- `p.and(q)`: true when **both** `p` and `q` are true.
- `p.or(q)`: true when **at least one** of `p` and `q` is true.
- `p.negate()`: inverts the boolean value of `p`.

Equivalent syntax in meaning:

```java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;

Predicate<Integer> positiveAndEven = positive.and(even);
Predicate<Integer> positiveOrEven = positive.or(even);
Predicate<Integer> notPositive = positive.negate();

System.out.println(positiveAndEven.test(8)); // true
System.out.println(positiveAndEven.test(3)); // false
System.out.println(notPositive.test(-2));    // true
```

### 2.1. Grouping Conditions According to Business Semantics

Suppose the requirement is: **Accept only paid orders**, and the order **must have an amount of at least 1,000,000 VND or belong to a VIP customer**. The logical rule must be:

```text
eligible = paid AND (meets minimum amount OR is VIP customer)
```

Java expresses this directly:

```java
Predicate<Order> paid = Order::paid;
Predicate<Order> minimumAmount = order -> order.amountVnd() >= 1_000_000L;
Predicate<Order> vipCustomer = order -> order.customerId().startsWith("VIP-");

Predicate<Order> eligible = paid.and(minimumAmount.or(vipCustomer));
```

Parentheses in the requirement matter greatly. `paid.and(minimumAmount).or(vipCustomer)` carries a different meaning: an **unpaid** VIP customer could still be selected. Naming and grouping expressions makes policy reviews much easier.

### 2.2. Understanding Short-Circuiting and Evaluation Order

`Predicate.and` and `Predicate.or` evaluate with *short-circuiting*, from left to right:

| Expression | When is `q.test(value)` skipped? | Reason |
| --- | --- | --- |
| `p.and(q)` | When `p` returns `false` | The final result is guaranteed to be `false` |
| `p.or(q)` | When `p` returns `true` | The final result is guaranteed to be `true` |

Consequently, you can place a safety check before a check that assumes valid data:

```java
Predicate<String> nonNull = java.util.Objects::nonNull;
Predicate<String> hasContent = text -> !text.isBlank();

Predicate<String> usableText = nonNull.and(hasContent);

System.out.println(usableText.test(null));   // false; does not call isBlank()
System.out.println(usableText.test("  "));    // false
System.out.println(usableText.test("Java"));  // true
```

Although short-circuiting can reduce expensive checks, **do not rely on side effects** inside a `Predicate`. Do not put counter increments, mandatory logging, or database updates inside conditional expressions assuming every condition will run.

## 3. Composing Functions to Build a Meaningful Transformation

`Function<T, R>` supports composing transformations in two ways:

- `f.andThen(g)`: applies `f` **first**, then applies `g`.
- `g.compose(f)`: applies `f` **first**, then applies `g`.

Both approaches produce the same result:

```java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> removeEdgeSpaces = String::strip;
Function<String, String> toLower = text -> text.toLowerCase(Locale.ROOT);

Function<String, String> normalizedA = removeEdgeSpaces.andThen(toLower);
Function<String, String> normalizedB = toLower.compose(removeEdgeSpaces);

System.out.println(normalizedA.apply("  JAVA@EXAMPLE.ORG  "));
// java@example.org

System.out.println(normalizedB.apply("  JAVA@EXAMPLE.ORG  "));
// java@example.org
```

You can read `removeEdgeSpaces.andThen(toLower)` from left to right: **strip leading/trailing spaces → convert to lowercase**. Meanwhile, `toLower.compose(removeEdgeSpaces)` reads as "perform the space-stripping step before calling the lowercase step".

To compose two `Function`s, the output type of the preceding step must be compatible with the input type of the following step:

```java
Function<String, Integer> length = String::length;

// String -> String -> Integer
Function<String, Integer> normalizedLength =
    removeEdgeSpaces.andThen(length);

System.out.println(normalizedLength.apply("  ABC  ")); // 3
```

If `Function<T, R>` changes the type from `T` to `R`, subsequent steps must be built to accept input `R`. You cannot chain two functions just because they share a conceptual name; Java must be able to verify types at compile time.

### 3.1. When to Use `Function.identity()`?

`Function.identity()` returns a function that keeps its input unchanged:

```java
Function<String, String> unchanged = Function.identity();
System.out.println(unchanged.apply("A-01")); // A-01
```

This method is useful in collectors or when an API requires a `Function` parameter yet the value needs no transformation. For example, when grouping strings into a map by their own content, `Function.identity()` can serve as the key mapper or value mapper, depending on the requirements and duplicate-key rules.

## 4. Combining Predicate and Function Properly

The two interface types can work together across multiple stages:

```text
                    Predicate<Order>          Function<Order, OrderView>
Order Source ── filter(eligible) ── Order ── map(toView) ── OrderView
                         │                            │
                   keep or discard             transform structure
```

With `Stream<T>`, `filter` accepts `Predicate<? super T>` and keeps the element type as `T`. `map` accepts a function converting from `T` to `R` and changes the stream's type to `Stream<R>`.

### 4.1. Complete Runnable Example: Applying Order Selection Rules and Producing Output

The following example compiles on **Java 17 and later** (using `record` and `Stream.toList()`):

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class OrderRuleDemo {
    record Order(
        String id,
        String customerId,
        long amountVnd,
        boolean paid
    ) {}

    record OrderView(String id, long amountVnd, String tier) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "C-01",   1_500_000L, true),
            new Order("O-02", "VIP-02",   300_000L, true),
            new Order("O-03", "VIP-03", 2_000_000L, false),
            new Order("O-04", "C-04",     600_000L, true)
        );

        Predicate<Order> paid = Order::paid;
        Predicate<Order> minimumAmount =
            order -> order.amountVnd() >= 1_000_000L;
        Predicate<Order> vipCustomer =
            order -> order.customerId().startsWith("VIP-");

        // Paid AND (meets minimum OR is VIP customer).
        Predicate<Order> eligible =
            paid.and(minimumAmount.or(vipCustomer));

        Function<Order, OrderView> toView = order -> new OrderView(
            order.id(),
            order.amountVnd(),
            order.customerId().startsWith("VIP-") ? "VIP" : "STANDARD"
        );

        List<OrderView> result = orders.stream()
            .filter(eligible)
            .map(toView)
            .toList();

        result.forEach(System.out::println);
    }
}
```

Output:

```text
OrderView[id=O-01, amountVnd=1500000, tier=STANDARD]
OrderView[id=O-02, amountVnd=300000, tier=VIP]
```

Breakdown of each order:

| Order | Paid | Amount ≥ 1 million | VIP customer | Result |
| --- | --- | --- | --- | --- |
| O-01 | Yes | Yes | No | Kept |
| O-02 | Yes | No | Yes | Kept |
| O-03 | No | Yes | Yes | Rejected because unpaid |
| O-04 | Yes | No | No | Rejected because criteria not met |

Because the rule is stored in the `eligible` variable and the transformation in `toView`, they can be reused in multiple places without copying the entire lambda expressions.

### 4.2. Transforming First, Then Checking

`filter` does not always come before `map`. If you want to check the **normalized value**, transform first and filter afterward:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Predicate;

List<String> rawEmails = java.util.Arrays.asList(
    "  MAI@EXAMPLE.ORG ",
    "support@other.org",
    null,
    "  AN@EXAMPLE.ORG "
);

Function<String, String> normalizeEmail =
    ((Function<String, String>) String::strip)
        .andThen(text -> text.toLowerCase(Locale.ROOT));

Predicate<String> belongsToExample =
    email -> email.endsWith("@example.org");

List<String> acceptedEmails = rawEmails.stream()
    .filter(Objects::nonNull)
    .map(normalizeEmail)
    .filter(belongsToExample)
    .toList();

System.out.println(acceptedEmails);
// [mai@example.org, an@example.org]
```

The `null` check is placed **before** `String::strip` to prevent `NullPointerException`. This example only illustrates checking a domain suffix; it is **not** a complete email address format validator. Production data requires format validation, normalization, and security rules suitable for the domain.

The key takeaway is: when inputs are unnormalized, applying `belongsToExample` before `map(normalizeEmail)` would wrongly reject strings containing uppercase letters and whitespace such as `"  MAI@EXAMPLE.ORG "`.

### 4.3. Creating a Predicate on the Source Type from a Function and a Predicate on the Target Type

Sometimes a check only knows how to work with type `R`, while the input data has type `T`. In that case, obtain `R` via `Function<T, R>` and pass it to `Predicate<R>`:

```java
// Assume Order is the record defined in example 4.1.
Function<Order, String> getCustomerId = Order::customerId;
Predicate<String> isVipId = id -> id.startsWith("VIP-");

// Adapter: Predicate<Order> built from Function<Order, String>
// and Predicate<String>.
Predicate<Order> orderFromVipCustomer =
    order -> isVipId.test(getCustomerId.apply(order));
```

You can express this relationship as a formula:

```text
Predicate<T> onSource =
    value -> predicateOnResult.test(function.apply(value))
```

`Predicate` does **not** have `compose` or `andThen` methods like `Function`. The adapter lambda above is a common way to bridge the two interface types.

If your goal is to **output the transformed value**, the clearer approach is usually `stream.map(function).filter(predicateOnResult)`. If you run `function.apply` inside `Predicate` and then run the same function again in `map`, the transformation may be executed twice. For expensive functions, design the pipeline to compute the result once, provided the processing order and data types still meet requirements.

## 5. Designing Reusable and Testable Rules

A maintainable rule set should have these traits:

1. **Business-descriptive names.** For instance, `paid`, `minimumAmount`, `eligible`, and `toView` are clearer than `p1`, `p2`, and `f`.
2. **Do one thing only.** `Predicate` tests; `Function` transforms. Avoid putting database writes or external variable updates inside filter and map expressions.
3. **Express null requirements explicitly.** Use `Objects::nonNull` or design the domain not to accept nulls in the first place. Do not assume every lambda handles null.
4. **Keep rules independent of how results are collected.** `Predicate` and `Function` can be used outside Streams—for example, in `if` statements, input validation, or transforming a single object.
5. **Test combinations and boundaries.** At a minimum, test amount thresholds, VIP exceptions, unpaid orders, and empty lists.

Example of reusing rules on a single object:

```java
Order oneOrder = new Order("O-05", "VIP-10", 200_000L, true);

if (eligible.test(oneOrder)) {
    OrderView view = toView.apply(oneOrder);
    System.out.println(view);
}
```

In this code, `eligible` and `toView` are accessible variables from example 4.1. This illustrates that **rules do not depend on Streams**; Streams merely provide one way to apply rules across multiple elements.

### Scenario Test Table

| Scenario | Input conditions | Expected |
| --- | --- | --- |
| Right at threshold | Paid, 1,000,000 VND, non-VIP | `eligible.test` returns `true` |
| Below threshold but VIP | Paid, 200,000 VND, VIP | `true` |
| Unpaid but VIP | Unpaid, 2,000,000 VND, VIP | `false` |
| Below threshold and non-VIP | Paid, 999,999 VND, non-VIP | `false` |
| Empty source list | No orders | `stream().filter(...).map(...).toList()` yields an empty list |

If a business rule changes—for example, "VIP customers must pay at least 100,000 VND"—update the expression creating the `Predicate` and add relevant test cases, leaving the `Function` creating `OrderView` untouched if the output format has not changed.

## 6. Lazy Pipelines, Short-Circuiting, and State

In the Java Stream API, `filter` and `map` are **intermediate operations**. Declaring the pipeline does not immediately run `Predicate.test` or `Function.apply`:

```java
var selected = orders.stream()
    .filter(eligible)
    .map(toView); // Does not traverse data at declaration time.

List<OrderView> views = selected.toList(); // Terminal operation consumes the Stream.
```

A Stream can only be consumed once; if you need another result, create a new pipeline from the source. Terminal operations can **short-circuit** or be optimized based on source characteristics. Never assume each `Predicate` or `Function` is always called exactly once per element: for example, `anyMatch` can stop as soon as a matching element is found, while some pipelines with `count` may be optimized to skip intermediate steps that do not affect the count.

### Why Avoid Shared State?

The following code is an example of **what not to do**:

```java
int[] counter = {0};

List<OrderView> views = orders.stream()
    .filter(order -> {
        counter[0]++; // Side effect inside Predicate.
        return eligible.test(order);
    })
    .map(toView)
    .toList();
```

This mixes counting with condition checking. The count depends on how the pipeline is executed; if switched to a parallel Stream, updating this array element can also cause a *data race*. If you need the count of results, use an appropriate terminal operation:

```java
long eligibleCount = orders.stream()
    .filter(eligible)
    .count();
```

For parallel pipelines, prefer **stateless** and **non-interfering** functions: do not modify the Stream source and do not update shared state while processing each element. Pure `Predicate`/`Function` implementations are usually friendlier to parallelization, though that does not automatically make `parallelStream()` faster. Performance depends on processing cost, data splitting, memory, ordering, and overhead; benchmark on real data.

When you need scans that depend on previous elements, or complex stateful rule sets, a loop may be clearer. Advanced techniques like custom collectors, `Spliterator`, or Stream Gatherers serve specific problems; you do not need them just to combine simple `Predicate` conditions and `Function` transformations.

## 7. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing `paid.and(minimumAmount).or(vipCustomer)` when payment is mandatory | Unpaid VIP customers still slip through | Use `paid.and(minimumAmount.or(vipCustomer))` |
| Calling `function.andThen(predicate)` | Type error: `Predicate` is not a `Function` | Use `stream.map(function).filter(predicate)` or an adapter lambda |
| Filtering on raw data before normalizing even though normalized data must be checked | Wrongly drops valid values | Place `map(normalize)` before `filter(predicate)` |
| Accessing properties of a potentially `null` value | `NullPointerException` | Check for null first or design inputs not to accept null |
| Counting or updating an external list inside `filter`/`map` | Unpredictable side effects, prone to parallel bugs | Use terminal operations like `count`, `toList`, or an appropriate collector |
| Reusing one Stream for two terminal operations | `IllegalStateException` when re-consumed | Create a new Stream from the source |
| Assuming `map` always runs for every element | Misunderstands laziness, short-circuiting, and optimizations | Do not rely on function side effects |
| Transforming in `Predicate` and transforming again in `map` | Duplicates work unnecessarily | Consider `map` before `filter` when only the transformed value is needed |

## 8. Practice Exercises

### Exercise 1: Candidate Filter

Given a list of candidates with `yearsOfExperience`, `javaSkill`, and `available`. Rule: a candidate must be available to work and have at least 3 years of experience **or** meet the required Java skill level. Write three separate `Predicate`s, combine them with `and`/`or` using proper parentheses, then `map` into a summary containing name and years of experience. Test the case of an unavailable candidate with very high skill.

### Exercise 2: Normalize Product Codes

Receive a `List<String>` that may contain `null`, whitespace, and mixed uppercase/lowercase letters. Normalize codes by calling `strip` and `toUpperCase(Locale.ROOT)`; keep only codes starting with `"PRD-"`. Write two `Function`s, compose them with `andThen`, then combine with a `Predicate` in a Stream. Explain why nulls must be filtered out before calling `strip`.

### Exercise 3: Distinguish Composition Order

Given `Function<String, String> trim`, `Function<String, Integer> length`, and `Predicate<Integer> atLeastFive`, build a pipeline keeping only strings whose **trimmed length is at least 5**. Compare `trim.andThen(length)` with `length.compose(trim)`. Write a `Predicate<String>` adapter from the corresponding two components and explain the risk of duplicate computation if you also `map` those same steps afterward.

### Exercise 4: Analyze Payment Rules

Replace the rule in example 4.1 with: "Paid, and **not in** the blocked customer group, and (meets threshold or VIP)". Add `Predicate<Order> blockedCustomer` and use `negate`. Create test data covering every branch, especially a VIP customer who is blocked.

### Exercise 5: Assess Parallelizability

Suppose a `Predicate` reads configuration data from a variable that can change while the pipeline runs. State the risks to results and synchronization when using `parallelStream()`. Propose a way to freeze the configuration into immutable data before running the pipeline, and explain why performance still needs to be measured before enabling parallel execution.

## 9. Knowledge Self-Check

- What does `Predicate<T>` return, and how does it differ from `Function<T,R>`?
- Why can `and`/`or` skip some condition evaluations?
- How do `f.andThen(g)` and `g.compose(f)` differ in how they are written yet share the same execution order?
- If you need to check a result **after** normalization, where should `filter` be placed relative to `map`?
- Why should you not use side effects inside `Predicate`/`Function` to count Stream elements?

**Takeaway:** Splitting a large rule into a **Predicate that checks conditions** and a **Function that transforms data** makes business logic clearer, easier to reuse, and easier to test. For correct results, always check **the scope of logical conditions, transformation order, null handling**, and the **lazy/short-circuit** nature of Streams.
