# Passing Business Rules via Predicate or Function in Java

## 1. Objectives

In many applications, **the processing workflow stays the same** while **the decision or calculation rules change**. For example, an order quoting workflow always goes through the steps of selecting valid orders, calculating prices, and returning results; however, the order selection criteria and pricing policies may vary across VIP customers, promotional campaigns, or individual sales channels.

Instead of writing multiple methods containing almost the same loop, Java can **accept business rules as behavioral objects**:

- **Predicate<T>**: a **checking/decision-making** rule that returns a **boolean**.
- **Function<T,R>**: a rule that **transforms an input T into a result R**.
- The orchestration API accepts these behaviors as **parameters**, so the processing flow remains stable while policies can be replaced or composed.

After this lesson, you will be able to identify suitable problems, design API signatures that accept functions, use lambdas and method references, combine conditions with Predicate, compose calculations with Function, use generic wildcards properly, test policies independently, and manage risks related to invalid data, side effects, and business errors.

## 2. The Essence of "Passing Business Rules"

A **business rule** is a decision or calculation that is meaningful to the application, for example:

- Is the order eligible for a discount?
- Should the order be included in the auto-approval list?
- Can a product be sold in the current market?
- What is the total amount after applying a discount policy?
- What result object should the input data be converted into?

In the **higher-order function** model, a method can **accept a function as a parameter**. In Java, a lambda is assigned to a functional interface and can be passed around as a value of that interface.

Minimal example:

~~~java
import java.util.function.Predicate;

static boolean approved(int score, Predicate<Integer> rule) {
    return rule.test(score);
}
~~~

This is an illustrative method that must be placed inside a class. When called:

~~~java
boolean strict = approved(75, score -> score >= 80);
boolean relaxed = approved(75, score -> score >= 70);
~~~

Result: **strict = false**, **relaxed = true**. The **approved** method is not modified; what changes is the **rule** provided by the caller.

Important note: this is a way to **separate the decision logic** from **the orchestration logic**, not to "allow arbitrary users to run Java code". Rules still need to be provided by code that has been trusted, tested, and deployed according to the application's processes.

## 3. Predicate<T>: Passing Conditional Rules

### 3.1. Signature and Meaning

`java.util.function.Predicate<T>` is a functional interface with the SAM:

~~~java
boolean test(T value);
~~~

It takes a T and returns **true/false**. In business logic, name the rule so that the meaning of `true` is clear: **isEligible**, **canPublish**, **passesRiskCheck**, **isValidOrder**.

Example of classifying orders by value:

~~~java
record Order(long totalVnd, boolean vip) { }

Predicate<Order> highValue =
        order -> order.totalVnd() >= 100_000;
Predicate<Order> vipCustomer =
        Order::vip;
~~~

The lines above illustrate the concept in a context where `java.util.function.Predicate` is already imported; they do not form a standalone Java file with a `main` method. Each rule can be passed to the same API:

~~~java
static List<Order> select(
        List<Order> orders,
        Predicate<? super Order> rule) {
    return orders.stream().filter(rule).toList();
}
~~~

This snippet requires importing `java.util.List`, having `Order`, and placing it inside a class. The caller decides the rule, while the `select` method is only responsible for iterating and selecting data.

### 3.2. Combining Small Rules

Predicate has the following default methods:

- **and(other)**: both conditions are true.
- **or(other)**: either condition is true.
- **negate()**: negates the condition.
- **Predicate.not(...)**: a convenient way to write negation in certain contexts.

~~~java
Predicate<Order> eligible = highValue.and(vipCustomer);
Predicate<Order> broad = highValue.or(vipCustomer);
Predicate<Order> notVip = vipCustomer.negate();
~~~

**and** and **or** use **short-circuit** evaluation: `and` does not evaluate the second operand if the first is false; `or` does not evaluate the second operand if the first is true. If a check can throw an exception, or if the first operand guards against null for the second, the order of checks must be chosen carefully.

Example:

~~~java
Predicate<String> notNull = text -> text != null;
Predicate<String> notBlank = text -> !text.isBlank();

Predicate<String> acceptable = notNull.and(notBlank);
System.out.println(acceptable.test(null)); // false
~~~

Checking for null before calling `isBlank()` helps avoid a NullPointerException. Reversing the order of the two predicates in the condition above could cause the program to fail on null.

### 3.3. Distinguishing Condition Checks from Error Validation

A `Predicate<Order>` only returns a boolean, so by itself it cannot explain **why an order was not selected**. If the business logic requires returning a full list of errors, error codes, or detailed messages, use a result type such as `ValidationResult` or a dedicated validation class instead of trying to cram all information into true/false.

**filter(rule)** is only appropriate when the application **intentionally discards** elements that do not meet the condition. For payment systems or data entry where error reporting is mandatory, silently filtering out records can violate business requirements.

## 4. Function<T,R>: Passing Calculation or Transformation Policies

### 4.1. Signature

`java.util.function.Function<T,R>` has the SAM:

~~~java
R apply(T value);
~~~

It transforms an input of type T into an output of type R. Unlike Predicate, the function is not restricted to returning a boolean.

Example:

~~~java
Function<Order, Long> regularPrice = Order::totalVnd;
Function<Order, String> orderLabel =
        order -> "Total=" + order.totalVnd();
~~~

These are illustrative snippets using the `Order` record described in section 3. An API can accept a policy to calculate the price:

~~~java
static <T, R> R applyPolicy(
        T item,
        Function<? super T, ? extends R> policy) {
    return policy.apply(item);
}
~~~

The `applyPolicy` method does not need to know the specific pricing or presentation logic; the caller decides the transformation rule.

### 4.2. Composing Transformations

`Function` has two important methods:

- **f.andThen(g)**: runs f first, then passes the result to g.
- **f.compose(g)**: runs g first, then passes the result to f.

~~~java
Function<Integer, Integer> addTwo = n -> n + 2;
Function<Integer, Integer> doubleIt = n -> n * 2;

int x = addTwo.andThen(doubleIt).apply(3); // 10
int y = addTwo.compose(doubleIt).apply(3); // 8
~~~

With the same input 3, the order of execution produces different results. In business logic, "rounding before calculating tax" and "calculating tax before rounding" can also differ; the order must not be changed arbitrarily.

When using pricing functions, clearly define **the currency unit, rounding policy, overflow handling, and which steps are allowed to be composed**. Function only provides the invocation structure; it does not determine financial rules on its own.

## 5. Separating Orchestration from Policy: Designing a General-Purpose API

Suppose a service receives a list of elements, a selection rule, and a transformation policy:

~~~java
static <T, R> List<R> process(
        List<T> items,
        Predicate<? super T> selected,
        Function<? super T, ? extends R> transform) {
    return items.stream()
            .filter(selected)
            .<R>map(transform)
            .toList();
}
~~~

This is an illustrative method and must be placed inside a class with `List`, `Predicate`, and `Function` imported.

Three separate responsibilities:

1. **items**: the source data.
2. **selected**: decides which items proceed.
3. **transform**: produces the result for each item that passes the condition.

Using generics **T,R** keeps the service independent of any specific business domain. The two wildcards are intentional:

- **Predicate<? super T>**: the Predicate can accept T or a supertype of T.
- **Function<? super T, ? extends R>**: the function can accept T/a supertype and return R/a subtype.

**Note on the syntax `.<R>map(transform)`:** this is an **explicit type witness** for `Stream.map`. It tells Java to fix the output element type of the stream to the exact R of the `process` method, rather than inferring a capture type of `? extends R` in certain contexts. There is no unsafe cast.

Advantage: no duplicating loops for each variant. Adding a new policy only requires providing a new Predicate/Function, as long as it matches the signature and business contract.

Limitation: `process` will execute whatever behavior the caller provides, including its errors or side effects; it does not guarantee on its own that the policies are correct, pure, or have the same performance.

## 6. Complete Java 17 Example: Order Selection and Quote Calculation

Problem:

- The system receives four orders.
- **Basic validity condition:** order is non-null, quantity is greater than 0, unit price is non-negative.
- **Policy A:** regular quote for all valid orders.
- **Policy B:** accepts only valid VIP orders, then applies a flat 5,000 VND discount to each order's total, without allowing a negative result.
- The service stays unchanged; only the two behavioral objects are swapped.

The example uses immutable records for `Order` and `Quote`; all monetary multiplications use `Math.multiplyExact` to detect overflow. Console printing operations are only in `main`.

Save the file **BusinessRuleDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Predicate;

public class BusinessRuleDemo {
    record Order(String id, int quantity, long unitPriceVnd, boolean vip) { }

    record Quote(String orderId, long totalVnd) { }

    static <T, R> List<R> process(
            List<T> items,
            Predicate<? super T> selected,
            Function<? super T, ? extends R> transform) {
        Objects.requireNonNull(items, "items");
        Objects.requireNonNull(selected, "selected");
        Objects.requireNonNull(transform, "transform");

        return items.stream()
                .filter(selected)
                .<R>map(transform)
                .toList();
    }

    static List<String> display(List<Quote> quotes) {
        return quotes.stream()
                .map(q -> q.orderId() + "=" + q.totalVnd())
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 2, 15_000, true),
                new Order("B", 1, 20_000, false),
                new Order("C", 1, 10_000, true),
                new Order("D", 0, 25_000, true)
        );

        Predicate<Order> valid = o -> o != null
                && o.quantity() > 0
                && o.unitPriceVnd() >= 0;

        Predicate<Order> vipAndValid = valid.and(Order::vip);

        Function<Order, Quote> regularPrice = o ->
                new Quote(
                        o.id(),
                        Math.multiplyExact((long) o.quantity(),
                                o.unitPriceVnd())
                );

        Function<Quote, Quote> discount = q ->
                new Quote(
                        q.orderId(),
                        Math.max(0L, q.totalVnd() - 5_000)
                );

        Function<Order, Quote> vipPrice =
                regularPrice.andThen(discount);

        List<Quote> regular = process(
                orders, valid, regularPrice);

        List<Quote> vip = process(
                orders, vipAndValid, vipPrice);

        System.out.println("Regular: " + display(regular));
        System.out.println("VIP: " + display(vip));
        System.out.println("Original size: " + orders.size());
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac BusinessRuleDemo.java
java BusinessRuleDemo
~~~

**Exact output:**

~~~text
Regular: [A=30000, B=20000, C=10000]
VIP: [A=25000, C=5000]
Original size: 4
~~~

### 6.1. Step-by-Step Walkthrough

- **valid** enforces positive quantity and non-negative unit price. Order **D** has quantity=0, so it is not selected.
- **vipAndValid** composes `valid.and(Order::vip)`. Order **B** has a valid quantity but is not VIP, so it only appears in the regular quote.
- **regularPrice** takes an Order and creates a new **Quote**. Order A has 2 × 15,000 = 30,000 VND; B has 20,000; C has 10,000.
- **discount** takes a calculated Quote and creates a new Quote reduced by 5,000, using `Math.max(0L,...)` to avoid producing a negative number. This is a **per-order fixed discount policy**, not a percentage discount or a discount across the whole list.
- **vipPrice = regularPrice.andThen(discount)** builds a new Function: calculate the regular price first, then apply the discount. For A this yields 25,000, and for C it yields 5,000.
- Both `process` calls use **the same iterate → filter → map algorithm**, while passing different policies.
- The **orders** list still has 4 elements. `stream().filter().map().toList()` does not remove elements from the source. The records in the example contain primitive and String fields, so no mutation occurs through these methods.

**Business limitations:** the example demonstrates non-negative amounts and avoiding overflow during multiplication, but it is not a production pricing engine: you must specify currency, taxes, exchange rates, discount application order, rounding, and total-sum checks when adding multiple amounts. Do not subtract amounts arbitrarily when data could be negative or already out of type bounds.

## 7. Why Is This Passing Behavior Rather Than Passing Results?

Compare the two approaches:

~~~java
// Pass a precomputed boolean value:
boolean allowed = someOrder.vip();

// Pass a rule to be applied to each Order:
Predicate<Order> rule = Order::vip;
~~~

In the first approach, `allowed` only describes the result for **one object at a single point in time**. In the latter, `rule` represents **behavior that can be executed repeatedly** on different Orders, allowing the service to decide when and which elements to check.

Similarly, `Function<Order,Quote>` is a rule that **creates a Quote from any matching Order**, not a pre-created Quote.

Passing behavior is especially useful when:

- Modules share the same processing flow but have different policies.
- Policies need to be configured by customer, channel, product, or time.
- Multiple policies need to be tested in unit tests without starting a database or web server.
- The same iterate, filter, and transform API needs to be reused across multiple data types.

Even so, do not overuse lambdas for large, multi-branch rules that are hard to name. For complex business logic, a clearly named `PricingPolicy` or `EligibilityPolicy` class with proper dependencies is easier to maintain.

## 8. Differences Between Predicate, Function, and Other Interfaces

| Interface | SAM | Typical Business Contract |
| --- | --- | --- |
| **Predicate<T>** | `boolean test(T t)` | Checks a true/false condition |
| **Function<T,R>** | `R apply(T t)` | Transforms or computes a result |
| **Consumer<T>** | `void accept(T t)` | Performs an action, returns no result |
| **Supplier<T>** | `T get()` | Supplies a value when called |
| **BiPredicate<T,U>** | `boolean test(T t,U u)` | Checks a condition requiring two inputs |
| **BiFunction<T,U,R>** | `R apply(T t,U u)` | Computes a result from two inputs |
| **UnaryOperator<T>** | `T apply(T t)` | A Function<T,T> for same-type transformation |

If an "is it eligible?" rule only needs true/false, choose Predicate. If you need to **explain why it is not eligible**, Predicate is not enough: use a result type that carries error details. If you need to **update the system** rather than return a value, Consumer or a clearly named business method may be more appropriate.

### 8.1. BiPredicate When a Rule Depends on Two Values

Example of an approval condition that needs an Order and a configuration:

~~~java
record Limit(long maxVnd) { }

BiPredicate<Order, Limit> withinLimit =
        (order, limit) -> order.totalVnd() <= limit.maxVnd();
~~~

This snippet is based on an Order type that has `totalVnd()`, **which differs from the Order record in the program in section 6** (which has quantity and unitPriceVnd). In real usage, you must define a consistent data model or create an appropriate total-calculation function.

You can bind the configuration into a single-parameter lambda:

~~~java
Limit currentLimit = new Limit(100_000);
Predicate<Order> rule =
        order -> withinLimit.test(order, currentLimit);
~~~

When `currentLimit` is a captured local variable, it must be **final or effectively final**. If you want to change configuration at runtime, do not silently read unmanaged global mutable state. Consider passing a configuration snapshot or updating the rule set at an explicit synchronization point.

## 9. Testing Policies Independently and Testing the API

Separating orchestration from rules enables two groups of unit tests:

**Group A — testing individual rules:**

- `valid.test(order)` returns false for quantity=0.
- `vipAndValid.test(order)` returns false if not VIP.
- `regularPrice.apply(order)` multiplies quantity and unit price accurately.
- `discount.apply(quote)` deducts exactly 5,000 and never produces a negative value.
- `regularPrice.andThen(discount)` preserves the order of calculating first, then discounting.

**Group B — testing the general workflow:**

- `process` only invokes the mapper on elements accepted by the Predicate.
- `process` preserves the encounter order of the input `List` when using a sequential stream.
- `process` returns an empty list for empty input.
- `process` rejects null function arguments according to the `Objects.requireNonNull` policy.
- If a Predicate/Function throws an exception, the service does not swallow the error and lets the caller handle it per the contract.

Example check right after creating `vip` in `main`:

~~~java
List<String> expected = List.of("A=25000", "C=5000");
if (!display(vip).equals(expected)) {
    throw new AssertionError("Unexpected VIP results");
}
~~~

This is an addition to the program in section 6; it is not a standalone file. In a real project, use JUnit and add test cases for boundary values, overflow, exceptions from policies, null values, and behavior when the input is mutated.

Do not just test "whether the function was called" while ignoring business meaning. The goal is to verify that **the policy is correct**, **the service executes the passed policy properly**, and **the input/output contract** is upheld.

## 10. Parameter Rules and Wildcards: Flexible Yet Type-Safe

The signature pair:

~~~java
Predicate<? super T>
Function<? super T, ? extends R>
~~~

is designed according to the **PECS** rule:

- `Predicate` accepts (consumes) a T, so it accepts a Predicate of T or a supertype of T.
- `Function` accepts T (consumer input) and produces R (producer output), so `? super T` for input and `? extends R` for output.

For example, an API processing Dog can accept `Predicate<Animal>`; a mapper taking Animal and returning String can still be used when the service expects CharSequence results.

~~~java
Predicate<Animal> hasName = animal -> animal.name() != null;
Function<Animal, String> label = Animal::name;

List<Dog> dogs = /* existing Dog data */;
List<CharSequence> labels =
        process(dogs, hasName, label);
~~~

This is a snippet in a context where Animal, Dog, and the `process` helper exist; it is not a standalone runnable program. It illustrates building an API that accepts broader behaviors without casting.

**Important:** concrete generic types in Java are still invariant. `Function<Animal,String>` is not automatically a `Function<Dog,CharSequence>`. Wildcards in **API parameters** are what describe a family of compatible behaviors.

Do not declare every variable with wildcards unnecessarily. Concrete implementations with clear names and exact types like `Function<Order,Quote>` are usually easier to read, infer types for, and invoke methods on.

## 11. Avoiding Side Effects in Predicate and Function

Callbacks may run multiple times, run only on certain elements, or be executed by a framework at a time the caller does not directly control. A policy should be as **predictable and testable** as possible.

Example of what **not** to do—depending on mutable global state that changes arbitrarily:

~~~java
static int promotionCounter = 0;

Predicate<Order> dependsOnCallCount = order ->
        ++promotionCounter % 2 == 0;
~~~

This is an illustrative snippet if placed inside a class with a static field and a suitable Order type. Two calls with the same Order may return different results. If switched to a parallel stream, `++` on a shared variable can also cause a race condition.

**Risks:**

- Unstable across repeated calls: the same input yields different results due to hidden state.
- Predicates with side effects can make evaluation order matter.
- `and/or` short-circuiting may skip calling the second operand.
- `Stream` is lazy and may optimize execution; do not put mandatory side effects inside `map/filter` and rely on callback invocation counts to execute business logic.
- `parallelStream` may run callbacks concurrently and does not guarantee side-effect execution order.

**Design direction:** pass policy values (discount amounts, thresholds, effective dates) as parameters or managed configuration objects. Separate database reads/writes, notifications, and mandatory logging from computational Predicates/Functions whenever possible.

Not every Function is a pure function—the interface only specifies the signature. "Purity" depends on the implementation and any state it accesses.

## 12. Error Management and Failure Policies

A Predicate can throw an exception, and so can a Function. The SAM signatures of `Predicate.test` and `Function.apply` **do not declare checked exceptions**; if a policy calls an API with checked exceptions, the author must catch/handle them or design a different abstraction.

Three common policies:

1. **Fail fast:** throw an exception upon encountering invalid data or calculations; the caller catches it and responds with an error.
2. **Accumulate errors as data:** use a type like `ValidationResult<T>` or a record containing error codes, messages, and data to return all issues; do not rely solely on Predicate.
3. **Intentional skipping:** use `filter` when business requirements allow discarding unsuitable elements. You can count or track skipped elements in the orchestration layer, but it must be clear why they were skipped.

In the example program, the `valid` policy excludes Quantity=0, which is an **explicit business choice**. If order D must be displayed as an "invalid order", the service should not merely filter it out; replace it with a classification or error-reporting pipeline.

### 12.1. Controlling Overflow and Monetary Data

`Math.multiplyExact` helps detect when multiplication overflows `long`. However, other subtraction, addition, or currency conversion operations also need similar policies. For currencies with decimal places, it is usually better to use `BigDecimal` with a specified scale and `RoundingMode`, rather than `double`.

If a policy reads fields from a mutable object or shared configuration, you must control mutations between steps. Using immutable records for input/output data can reduce some risks, but **records do not provide deep immutability** if they contain mutable objects.

### 12.2. Which Policy Is Responsible for Validation?

You cannot assume that because the service has a Predicate, every Function will always receive valid input: other callers can still invoke the Function directly. Critical **domain invariants** should usually be protected in constructors or domain methods, while the orchestration API documents its preconditions clearly.

For example, if a Quote must never be created with a negative total, the Quote constructor can enforce that check; in the learning example, the rule is expressed through the policy using `Math.max`. The exact organization depends on the level of guarantee the system requires.

## 13. When Should You Use a Named Business Interface?

`Predicate<Order>` is great for short, clear conditions. But if a policy needs:

- Version names, policy codes, effective dates;
- Complex configuration parameters;
- Structured error responses or decision explanations;
- Multiple calculations or multiple related methods;
- Resources with lifecycles and specialized dependencies;

then a named business interface may be easier to manage:

~~~java
interface PricingPolicy {
    Quote calculate(Order order);
}
~~~

This is an illustrative snippet based on Order and Quote from the program in section 6, not a standalone file.

This interface is **structurally a functional interface** if it has exactly one abstract method, so it can still be implemented with a lambda:

~~~java
PricingPolicy policy = order ->
        new Quote(order.id(), 0L);
~~~

Use the `0L` example only to see the syntax; **do not treat it as a valid production pricing rule**. A clearly named class implementing PricingPolicy is a sensible choice when business logic is large or requires dependency injection. APIs accepting Predicate/Function and a domain interface are not mutually exclusive: both are ways of passing behavior, with different levels of domain expressiveness.

## 14. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Passing a **boolean** when you want to pass a rule | Only checks one object; no reusable behavior | Pass a Predicate<T> |
| Using Predicate to return error messages | Boolean cannot carry failure reasons | Use a validation result type |
| Using Function with hidden side effects | Policy is hard to test and depends on order/invocation | Return new values and separate I/O |
| Calling `Predicate.and` while forgetting short-circuiting | The second operand may not run | Do not put mandatory side effects in predicates |
| Changing the order of composed Functions | Monetary or validation results change | Document ordering contracts and write specific tests |
| Multiplying money without overflow checks | Can return incorrect totals | Use Math.multiplyExact and appropriate arithmetic rules |
| Using `Function<T,R>` too narrowly in APIs | Hard to reuse functions accepting supertypes/returning subtypes | Consider `Function<? super T,? extends R>` |
| Filtering out invalid data without error reporting | Records are lost silently | Separate into an error-classification flow if needed |
| Assuming streams automatically roll back when a mapper fails | Work with side effects may already have persisted | Design transactions and side-effect boundaries |
| Putting global mutable policy state inside callbacks | Non-reproducible results, race condition risk | Use snapshots, dependency injection, or synchronization |

## 15. Practice Exercises

### Exercise 1: Filtering Candidates

A system has the record:

~~~java
record Candidate(String name, int experienceYears, boolean certified) { }
~~~

Write a Predicate that selects candidates who have **at least 2 years of experience** and **are certified**.

**Hint:**

~~~java
Predicate<Candidate> enoughExperience =
        c -> c.experienceYears() >= 2;
Predicate<Candidate> certified = Candidate::certified;

Predicate<Candidate> eligible =
        enoughExperience.and(certified);
~~~

These snippets can be placed in a class that imports Predicate and declares record Candidate. Test with candidates having 1 or 2 years of experience and `certified` set to true/false.

### Exercise 2: Passing Functions to the Same API

A list of quantities `List<Integer>` needs to be processed under two policies:

- Policy A: double each value.
- Policy B: add 10.

**Hint:**

~~~java
Function<Integer, Integer> doubleIt = n -> n * 2;
Function<Integer, Integer> plusTen = n -> n + 10;

List<Integer> values = List.of(1, 2, 3);
List<Integer> first = process(
        values, n -> true, doubleIt);
List<Integer> second = process(
        values, n -> true, plusTen);
~~~

With the `process` helper from section 5, **first = [2, 4, 6]** and **second = [11, 12, 13]**. This is a snippet rather than a standalone runnable file; do not use `n -> true` if a real problem has a data-selection rule that must be verified.

### Exercise 3: Adding a Discount Policy

In BusinessRuleDemo, replace the fixed 5,000 VND discount policy with a **10%** discount for VIP orders. Define the rounding rule before coding, and test with an order whose total is not divisible by 10. Keep `process` unchanged; just create a different Function and pass it when calling.

**Hint:** you can write a Function<Order, Quote> applying Math.multiplyExact and the appropriate percentage calculation, or compose Function<Order,Quote> with Function<Quote,Quote>. Avoid using `double` if exact monetary precision is required; choose `BigDecimal`/`long` depending on the smallest currency unit and rounding contract.

### Exercise 4: Choosing the Right API

A system needs to approve applications and **return the reason for rejection**. Should it be designed with only `Predicate<Application>`?

**Answer:** Predicate is appropriate if the caller only needs true/false. If the reason is needed, use `Function<Application, Decision>` or a named interface with a `Decision` type containing the status and reason. That way you can still pass behavior, while the returned data captures the business contract.

### Exercise 5: Designing Tests

Write tests for the `process` service with empty input, null policy, a policy that throws an exception, and a list containing both matching and non-matching elements. Verify that only matching elements are transformed; if the policies are pure functions, the tests do not depend on global state.

## 16. Key Takeaways

**Passing business rules via Predicate or Function** means **moving the decision/calculation logic into API parameters**, so that the orchestration flow can be reused without duplicating code:

- **Predicate<T> — boolean test(T)**: checks conditions, composed with `and/or/negate`.
- **Function<T,R> — R apply(T)**: produces results, composed with `andThen/compose`.
- **API accepting functions**: separates **data + workflow** from **varying policies**; use `? super` and `? extends` wildcards when helpful.
- **Clear policies**: well-named, with input/output contracts, null/error handling, overflow control, and domain invariants.
- **Testing**: verify both individual rules and the workflow that applies them; do not confuse data filtering with mandatory error reporting.

This approach makes a service flexible across many business scenarios while remaining readable, testable, and loosely coupled between classes.
