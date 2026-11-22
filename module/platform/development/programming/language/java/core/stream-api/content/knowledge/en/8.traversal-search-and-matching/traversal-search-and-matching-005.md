# Understanding Matching Results on an Empty Stream

In the Java Stream API, `anyMatch`, `allMatch`, and `noneMatch` answer three different questions about a set of elements. A common point of confusion is: **when a Stream is empty, both `allMatch` and `noneMatch` return `true`, while `anyMatch` returns `false`**. This is the intentional semantics of logical quantification, not a bug in Java.

This lesson belongs to the **Traversal, Search, and Matching** chapter of the **JAVA_STREAM_API** module. A clear grasp of the empty Stream case helps you write `filter`, `map`, search, and aggregation pipelines that match business logic, especially with empty inputs or inputs where everything is filtered out. It also provides the foundation for evaluating the effects of **laziness**, *short-circuiting*, parallel processing, shared state, and performance in the Java Stream API.

## 1. The Three Matching Operations and Results on an Empty Stream

A matching operation applies a `Predicate<T>` (a function returning `boolean`) to the elements of a `Stream<T>`. All three are **terminal operations**: they consume the Stream and return a single `boolean` value.

| Method | Question about elements | Must an element match to return `true`? | Empty Stream |
| --- | --- | --- | --- |
| `anyMatch(predicate)` | Is there **at least one** element matching the condition? | Yes | **`false`** |
| `allMatch(predicate)` | Do **all** elements match the condition? | Does not require the Stream to have elements | **`true`** |
| `noneMatch(predicate)` | Do **no** elements match the condition? | No; simply requires no matching cases | **`true`** |

Minimal example:

```java
import java.util.stream.Stream;

public class EmptyMatchBasics {
    public static void main(String[] args) {
        boolean anyPositive = Stream.<Integer>empty()
            .anyMatch(number -> number > 0);

        boolean allPositive = Stream.<Integer>empty()
            .allMatch(number -> number > 0);

        boolean nonePositive = Stream.<Integer>empty()
            .noneMatch(number -> number > 0);

        System.out.println(anyPositive);  // false
        System.out.println(allPositive);  // true
        System.out.println(nonePositive); // true
    }
}
```

Here **three fresh Streams** are used, because each Stream can execute a terminal operation only once. `Stream.<Integer>empty()` creates an empty source with a specific element type. No numbers are passed to the `number > 0` lambdas.

### What Makes the Result Look Unusual?

Reading too quickly can lead to two wrong conclusions:

- “`allMatch` returning `true` means there are valid elements.” In reality, it **does not confirm any elements exist**.
- “`noneMatch` returning `true` means all elements are invalid.” In reality, it only confirms **there are no elements matching the given predicate**.

For example, if a registration list is empty, both statements “all registrations meet the standard” and “no registrations meet the standard” are considered true under quantified logic. They do not contradict each other, because the set of registrations has no member to serve as a counterexample to the first statement or a positive example for the second.

## 2. Understanding via Mathematical Logic: *Vacuous Truth*

The three matching operations correspond to three types of propositions:

- `anyMatch(p)` is **there exists** an element `x` such that `p(x)` is true (written `∃x: p(x)`).
- `allMatch(p)` is **for all** elements `x`, `p(x)` is true (written `∀x: p(x)`).
- `noneMatch(p)` is **there exists no** element `x` such that `p(x)` is true (written `¬∃x: p(x)`).

If the dataset is empty:

- No element exists, so `anyMatch(p)` is `false`.
- No element **violates** the condition, so `allMatch(p)` is `true`.
- No element **satisfies** the condition, so `noneMatch(p)` is `true`.

The statement “every element of the empty set satisfies the condition” is called *vacuously true*. A more intuitive way to view it: `allMatch` looks for **a counterexample** that disproves “all are true”; in an empty Stream, no counterexample can be found.

For a finite set, the matching operations can be viewed as:

```text
anyMatch(p)   = there is at least 1 element with p(x) == true
allMatch(p)   = there is no element with p(x) == false
noneMatch(p)  = there is no element with p(x) == true

Element count = 0
  ├── anyMatch  → false
  ├── allMatch  → true
  └── noneMatch → true
```

This is the semantics of the quantification operations in Java, regardless of whether the condition passed in is simple or complex.

## 3. Truth Table by Number of Matching Elements

Suppose `p` is “number greater than 0”. The table below shows results as the input varies:

| Stream data | Element count | Elements matching `p` | `anyMatch(p)` | `allMatch(p)` | `noneMatch(p)` |
| --- | ---: | ---: | :---: | :---: | :---: |
| `[]` | 0 | 0 | `false` | **`true`** | **`true`** |
| `[1]` | 1 | 1 | `true` | `true` | `false` |
| `[-1]` | 1 | 0 | `false` | `false` | `true` |
| `[1, 2]` | 2 | 2 | `true` | `true` | `false` |
| `[1, -2]` | 2 | 1 | `true` | `false` | `false` |
| `[-1, -2]` | 2 | 0 | `false` | `false` | `true` |

Looking at the table, pay special attention to:

1. When there is **at least one** element, `anyMatch` and `noneMatch` cannot both be true.
2. When the set is empty, having both `allMatch` and `noneMatch` be true is completely valid.
3. If every element satisfies the condition in a **non-empty** set, both `allMatch` and `anyMatch` are true.
4. `anyMatch(p)` only needs one satisfying example; `allMatch(p)` only needs one counterexample to be false.

You can run the following example to compare:

```java
import java.util.List;

List<Integer> numbers = List.of(1, -2);

System.out.println(numbers.stream().anyMatch(n -> n > 0));  // true
System.out.println(numbers.stream().allMatch(n -> n > 0));  // false
System.out.println(numbers.stream().noneMatch(n -> n > 0)); // false
```

## 4. A Stream Can Become Empty at Different Stages

“Empty Stream” does not only mean the initial input list is empty. In real applications, data can be completely filtered out in intermediate steps.

### 4.1. Data Source Has No Elements

```java
import java.util.List;

List<String> names = List.of();

boolean anyLongName = names.stream()
    .anyMatch(name -> name.length() > 10);

boolean allNonBlank = names.stream()
    .allMatch(name -> !name.isBlank());

System.out.println(anyLongName); // false
System.out.println(allNonBlank);  // true
```

Even if the business requirement says “there must be valid names”, `allMatch` alone still does not detect an empty list.

### 4.2. Source Has Data, but `filter` Excludes Everything

```java
import java.util.List;

record Order(String id, long amountVnd, boolean paid) {}

List<Order> orders = List.of(
    new Order("O-01", 200_000L, true),
    new Order("O-02", 350_000L, false)
);

// No order reaches the 1 million threshold.
boolean allExpensiveOrdersPaid = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .allMatch(Order::paid);

System.out.println(allExpensiveOrdersPaid); // true
```

Even though `orders` is non-empty, the Stream **after `filter`** is empty. `allMatch` returns `true` because there is no unpaid high-value order to refute the condition.

This is why you must pinpoint the exact question:

- “**Is there any unpaid expensive order?**” → `anyMatch` on the condition “expensive and unpaid”.
- “**Are all expensive orders paid?**” → `filter(...).allMatch(Order::paid)`; accepts the case where there are no expensive orders.
- “**Is there at least one expensive order and are all expensive orders paid?**” → must check **non-emptiness** on the *filtered* set as well as `allMatch`.

Do not treat a `true` result from `allMatch` as proof that source data or selected data exists.

### 4.3. Other Operations Can Also Produce Empty Output

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

System.out.println(Stream.of("A", "B")
    .limit(0)
    .allMatch(s -> !s.isBlank())); // true

System.out.println(IntStream.range(5, 5)
    .noneMatch(n -> n < 0));       // true

System.out.println(Stream.of("1", "2")
    .filter(s -> s.equals("X"))
    .anyMatch(s -> s.length() > 0)); // false
```

`limit(0)` takes 0 elements; `IntStream.range(5, 5)` is an empty half-open interval; `filter` can select an empty set. All three situations follow the same truth table for matching operations.

## 5. When Business Logic Requires “At Least One and All Pass”

This is the most critical distinction to settle cleanly in data validation, approvals, transactions, or quality checks.

Suppose the requirement is: **There must be at least one order worth at least 1 million VND and all such orders must be paid.**

Merely writing:

```java
boolean approved = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .allMatch(Order::paid);
```

is **insufficient**. The result is `true` if no order meets the threshold.

### 5.1. Clear Approach: Capture Candidates Then Check

```java
import java.util.List;

List<Order> expensiveOrders = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .toList();

boolean approved = !expensiveOrders.isEmpty()
    && expensiveOrders.stream().allMatch(Order::paid);

System.out.println(approved); // false for the list in section 4.2
```

This separates the two requirements into two conditions:

1. `!expensiveOrders.isEmpty()`: there are genuinely candidates to evaluate.
2. `expensiveOrders.stream().allMatch(Order::paid)`: no candidate violates the requirement.

`&&` evaluates lazily (short-circuits): if the candidate list is empty, `allMatch` does not need to run. This approach fits well when the filtered set is also needed for subsequent steps, though `toList()` stores the results in memory.

### 5.2. Without Storing an Intermediate List: Two Checks

With a source that is a stable `List` during validation, you can use two independent pipelines:

```java
boolean hasExpensiveOrder = orders.stream()
    .anyMatch(order -> order.amountVnd() >= 1_000_000L);

boolean allExpensivePaid = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .allMatch(Order::paid);

boolean approved = hasExpensiveOrder && allExpensivePaid;
```

This avoids creating an intermediate list, though it may traverse the source multiple times. Each call to `orders.stream()` creates **a fresh Stream**: the same Stream cannot be consumed twice. If the source mutates between the two checks or can only be read once (such as a file stream), use a different strategy to guarantee consistent results.

If you only need the question “is there at least one **unpaid** order in the expensive group?”, it can be expressed more concisely:

```java
boolean hasUnpaidExpensiveOrder = orders.stream()
    .anyMatch(order ->
        order.amountVnd() >= 1_000_000L && !order.paid()
    );
```

However, negating this result **does not** prove an expensive order exists: if no order meets the threshold, `hasUnpaidExpensiveOrder` is still `false`. When proof of existence is required, check explicitly.

### 5.3. Choose by Business Meaning, Not Statement Length

| Actual requirement | Expression | When there are no candidates |
| --- | --- | --- |
| At least one candidate satisfies `p` | `anyMatch(p)` | `false` |
| No candidate violates `p` | `allMatch(p)` | `true` |
| No candidate has forbidden property `p` | `noneMatch(p)` | `true` |
| Must have candidates **and** all satisfy `p` | `!candidates.isEmpty() && candidates.stream().allMatch(p)` | `false` |
| Must have candidates **and** none violate `p` | `!candidates.isEmpty() && candidates.stream().noneMatch(p.negate())` | `false` |

In the table, `candidates` must be **the exact set actually being matched**, which may be the output of `filter`. Checking `!orders.isEmpty()` before `filter` is not enough if `filter` still drops every order.

## 6. Logical Relationships Between Matching Operations

Given a pure condition `p` that does not depend on external state, the following relationships hold on both empty and non-empty Streams:

```text
noneMatch(p)  is equivalent to  !anyMatch(p)

allMatch(p)   is equivalent to  !anyMatch(not p)

noneMatch(p)  is equivalent to  allMatch(not p)
```

Logical example (each expression must run on a fresh Stream):

```java
import java.util.List;
import java.util.function.Predicate;

List<Integer> values = List.of();
Predicate<Integer> positive = n -> n > 0;

boolean a = values.stream().noneMatch(positive);
boolean b = !values.stream().anyMatch(positive);

boolean c = values.stream().allMatch(positive);
boolean d = !values.stream().anyMatch(positive.negate());

System.out.println(a == b); // true
System.out.println(c == d); // true
System.out.println(c);      // true, because values is empty
```

The negation `!` flips the question being asked, but **does not force the Stream to have elements**. Therefore, replacing `allMatch(p)` with `!anyMatch(p.negate())` does not solve the “at least one element” requirement.

The equivalences above assume the condition has stable semantics. If `Predicate` has side effects, depends on time, randomness, or mutable state, two independent pipelines may observe different data. In that case, fix the data and condition design before relying on logical transformations.

## 7. Laziness, Early Stopping, and Predicate Evaluation Counts

`filter`, `map`, and many other intermediate operations are **lazy**; the condition inside `anyMatch`, `allMatch`, or `noneMatch` is applied only when the terminal operation needs to inspect an element.

All three matching operations **short-circuit**: they can stop as soon as the outcome is determined.

| Method | Can stop upon encountering | Reason |
| --- | --- | --- |
| `anyMatch(p)` | An element where `p` returns `true` | “Exists” is proven. |
| `allMatch(p)` | An element where `p` returns `false` | A counterexample is found. |
| `noneMatch(p)` | An element where `p` returns `true` | “None exists” is disproven. |

On an empty Stream, all three matching operations return a result with **zero calls to `Predicate.test`**. On a non-empty Stream, do not assume every element is inspected.

```java
import java.util.List;

List<Integer> numbers = List.of(2, 4, 6, 7, 8);

boolean hasOdd = numbers.stream()
    .anyMatch(n -> n % 2 != 0); // true; may stop at 7

boolean allEven = numbers.stream()
    .allMatch(n -> n % 2 == 0); // false; may stop at 7

boolean noOdd = numbers.stream()
    .noneMatch(n -> n % 2 != 0); // false; may stop at 7
```

The examples above are sequential pipelines on an ordered `List`. With `parallelStream()`, the count and order of `Predicate` invocations may differ from sequential execution; the logical result must still hold if `Predicate` meets the **stateless** and **non-interfering** requirements.

### Why Should Side Effects Inside a Predicate Be Avoided?

Do not use `anyMatch` or `allMatch` as an “implicit loop” to update an external variable:

```java
int[] inspectedCount = {0};

boolean anyPaid = orders.stream()
    .anyMatch(order -> {
        inspectedCount[0]++; // Not a reliable representation of total orders.
        return order.paid();
    });
```

If a paid order is encountered early, `anyMatch` can stop without traversing all orders; on an empty Stream, `inspectedCount[0]` stays 0; on a parallel Stream, mutating a shared array can cause a *data race*. If you need to count all matching elements, use `filter(...).count()`; if you need to find one element, use `findFirst` or `findAny` with clear result handling.

## 8. Distinguishing Matching from Searching and Counting on Empty Streams

Related terminal operations return different data types. The following table uses a genuinely empty Stream:

| Operation | Return type | Result when empty |
| --- | --- | --- |
| `anyMatch(p)` | `boolean` | `false` |
| `allMatch(p)` | `boolean` | `true` |
| `noneMatch(p)` | `boolean` | `true` |
| `count()` | `long` | `0L` |
| `findFirst()` | `Optional<T>` | `Optional.empty()` |
| `findAny()` | `Optional<T>` | `Optional.empty()` |
| `IntStream.average()` | `OptionalDouble` | Empty |
| `IntStream.sum()` | `int` | `0` |

Illustration:

```java
import java.util.Optional;
import java.util.stream.IntStream;
import java.util.stream.Stream;

Optional<String> first = Stream.<String>empty().findFirst();
long count = Stream.<String>empty().count();
boolean any = Stream.<String>empty().anyMatch(s -> s.startsWith("A"));
int total = IntStream.empty().sum();

System.out.println(first.isPresent()); // false
System.out.println(count);             // 0
System.out.println(any);               // false
System.out.println(total);             // 0
```

Do not write `findFirst().isPresent()` just to answer “is there an element matching `p`?” when `anyMatch(p)` already expresses that question directly. `findFirst` fits when you need **to retrieve the element** for further processing, while `anyMatch` fits when you only need a `boolean` result.

Conversely, if you must distinguish “no data to evaluate” from “there is data, but all failed”, a single `boolean` from `anyMatch` is not enough. You can also capture `count`, retain the candidate set, or design a result type that explicitly represents the **no data** state.

### Characteristics of Primitive Streams

`IntStream`, `LongStream`, and `DoubleStream` also have `anyMatch`, `allMatch`, and `noneMatch`; they accept specialized functional interfaces such as `IntPredicate`. On an empty source, the triplet of results remains `false, true, true`:

```java
import java.util.stream.IntStream;

boolean any = IntStream.empty().anyMatch(n -> n > 0);
boolean all = IntStream.empty().allMatch(n -> n > 0);
boolean none = IntStream.empty().noneMatch(n -> n > 0);

System.out.println(any + ", " + all + ", " + none);
// false, true, true
```

Converting from `Stream<Integer>` to `IntStream` via `mapToInt` does not alter logical semantics on an empty set.

## 9. Practical Example: Validating a Set of Payment Records

The following Java 17+ example uses `record`, extracts a set of invoices due for reconciliation, and applies the policy **“there is at least one due invoice, and all of them must be paid”**.

```java
import java.util.List;

public class EmptyMatchingDemo {
    record Invoice(String id, boolean due, boolean paid) {}

    static boolean approveDueInvoices(List<Invoice> invoices) {
        // Consider only invoices that are due.
        List<Invoice> dueInvoices = invoices.stream()
            .filter(Invoice::due)
            .toList();

        // Separate the existence check from the all-pass check.
        return !dueInvoices.isEmpty()
            && dueInvoices.stream().allMatch(Invoice::paid);
    }

    static boolean everyDueInvoicePaid(List<Invoice> invoices) {
        // This logical statement allows the due-invoice set to be empty.
        return invoices.stream()
            .filter(Invoice::due)
            .allMatch(Invoice::paid);
    }

    public static void main(String[] args) {
        List<Invoice> empty = List.of();

        List<Invoice> notYetDue = List.of(
            new Invoice("I-01", false, false)
        );

        List<Invoice> allPaid = List.of(
            new Invoice("I-02", true, true),
            new Invoice("I-03", true, true)
        );

        List<Invoice> hasUnpaid = List.of(
            new Invoice("I-04", true, true),
            new Invoice("I-05", true, false)
        );

        System.out.println(approveDueInvoices(empty));      // false
        System.out.println(approveDueInvoices(notYetDue));  // false
        System.out.println(approveDueInvoices(allPaid));    // true
        System.out.println(approveDueInvoices(hasUnpaid));  // false

        System.out.println(everyDueInvoicePaid(empty));     // true
        System.out.println(everyDueInvoicePaid(notYetDue)); // true
        System.out.println(everyDueInvoicePaid(hasUnpaid)); // false
    }
}
```

The example demonstrates two distinct policies:

- **`everyDueInvoicePaid`** states “no due invoice is unpaid”. If there are no due invoices, the proposition still holds.
- **`approveDueInvoices`** states “due invoices exist for reconciliation, and all of them are paid”. When candidate data is missing, do not approve.

Both ways of writing can be right, but right for **two different business rules**. In real systems, a “no records” condition might also mean “data has not synced yet” or “no data found in the requested period”. In such cases, whether to allow approval or report an insufficient-data status must be clearly defined before choosing the matching operation.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `allMatch` to check “at least one and all are valid” | Empty Stream still returns `true` | Add a non-empty check on the candidate set. |
| Checking `!source.isEmpty()` but forgetting `filter` may drop everything | Source has data, but evaluated set is empty | Check after filtering or check existence with the same filter predicate. |
| Thinking `noneMatch(p)` means there are elements failing `p` | Empty set is misinterpreted | Understand it accurately as **no element exists matching `p`**. |
| Thinking `allMatch(p)` and `noneMatch(p)` cannot both be true | Misunderstanding vacuous truth | Both are `true` on an empty set. |
| Replacing `allMatch(p)` with `!anyMatch(!p)` to fix empty sets | Still `true` on an empty set | To require at least one element, check existence separately. |
| Reusing one Stream to call `anyMatch` and `allMatch` | `IllegalStateException` because the Stream was consumed | Create a fresh Stream from the source or store candidates if needed. |
| Putting side effects in `Predicate`, assuming full traversal | Wrong counts, unpredictable behavior, parallel bugs | Use `count` to count, avoid shared state inside matching. |
| Treating `false` from `anyMatch` as proof data exists with no matches | Fails to distinguish empty source from zero matches | Track data existence separately if business logic needs it. |
| Enabling `parallelStream` and relying on predicate call order | Unpredictable side effects, potential thread-safety bugs | Use pure predicates without relying on order or call counts. |

## 11. Practice Exercises

### Exercise 1: Predict Results When Data Is Empty

Given:

```java
List<Integer> values = List.of();
```

Predict the results of these expressions and explain each one:

```java
values.stream().allMatch(n -> n > 100);
values.stream().anyMatch(n -> n > 100);
values.stream().noneMatch(n -> n > 100);
values.stream().filter(n -> n < 0).allMatch(n -> n % 2 == 0);
```

Hint: determine how many elements the Stream has **right at the matching operation**, instead of looking only at the `Predicate` expression.

### Exercise 2: Non-Empty Source, Empty Candidates

Given an order list with amounts `100_000L` and `200_000L`. Filter orders with amounts `1_000_000L` or more and then check `allMatch(Order::paid)`. Why can this return `true` even though no order reached the threshold? Add a condition to require **at least one qualifying order**.

### Exercise 3: Write a Validity Policy for a Student Group

A project-group grading system requires: “A group must have at least one member, and every member must have a participation score of at least 60”. Write a method accepting `List<Student>` and returning `boolean`. Test three scenarios: empty group, group with one passing student, and group with one failing student.

### Exercise 4: Proof of Non-Existence

Write two equivalent expressions to check that there are **no negative numbers** in a `List<Integer>`:

1. Using `noneMatch(n -> n < 0)`.
2. Using `allMatch(n -> n >= 0)`.

Test with an empty list. Then rewrite when the business rule requires **the list must be non-empty and contain no negative numbers**.

### Exercise 5: Verifying Early Stopping

Given a `List<Integer>` containing one negative number in the middle of the list. Predict whether `anyMatch(n -> n < 0)` needs to check elements after that negative number. Why should you not use the lambda to increment a shared counter and treat it as the source's element count?

### Exercise 6: Designing a “No Data” State

Build a function evaluating batch quality with three outcomes: `NO_DATA`, `PASS`, and `FAIL`. Input is `List<Item>`, each element having an inspection status. Describe how to detect an empty batch before using `allMatch` to validate. Why might returning a single `boolean` fail to meet the requirement?

## 12. Knowledge Self-Check

- Why does `allMatch` return `true` on an empty Stream?
- Why does `noneMatch` also return `true` on that same Stream?
- What causes `anyMatch` to return `false` when a Stream has no elements?
- If `filter` eliminates all data, what do subsequent matching operations return?
- When requiring “at least one element and all are valid”, what additional check is needed?
- Is `allMatch(p)` equivalent to `!anyMatch(p.negate())` on an empty Stream?
- Why should you not infer element count or traversal order from the number of `Predicate` calls?
- When is a three-state result needed instead of a `boolean`?

**Key Takeaway:** On an empty Stream, the trio of results is always **`anyMatch = false`, `allMatch = true`, `noneMatch = true`**. This is the logical semantics of the matching operations. When business logic requires **data to actually be present for evaluation**, explicitly check the existence of the candidate set, especially if the pipeline contains `filter` or operations capable of producing an empty Stream.
