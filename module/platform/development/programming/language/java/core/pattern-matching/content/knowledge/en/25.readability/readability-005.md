# Avoid Patterns Just to Shorten Code: Prioritize Readability in Java

## 1. Lesson Objectives

Pattern matching helps Java eliminate many manual `instanceof` + cast blocks, perform safe type recognition, and deconstruct records. However, **shorter code is not automatically more readable code**. A nested record pattern spanning multiple levels, combined with `when` and business conditions, can take a reader more time to understand than a method with a clear, meaningful name.

This lesson focuses on the **readability** criterion: when a pattern helps express intent, when it merely replaces several lines of syntax with a hard-to-read expression, how to choose the right level of deconstruction, and how to prove a refactor does not change behavior.

After completing this lesson, you will be able to:

- Distinguish **reducing boilerplate** from **reducing cognitive complexity**.
- Choose between shallow type patterns, nested record patterns, and named domain methods.
- Organize guards, `null` conditions, and fallback branches so they are easy to understand at a glance.
- Review a pattern change by **meaning** and **behavior**, not by line count.
- Know when a pattern is the clearest choice, rather than avoiding patterns altogether.

The main examples use Java 21, because **record patterns** (JEP 440) and **pattern matching for switch** (JEP 441) are standard features as of this version. Type patterns in `instanceof` have been standardized since Java 16 (JEP 394).

## 2. Don't Optimize by Line Count

Look at two ways of expressing the same idea in a simulated shipping example:

**A deeply structured branch:**

```java
case Order(var id,
           Customer(var name, Address(var city, var country)),
           var status)
        when status == PaymentStatus.PAID
             && "VN".equals(country)
             && "HCM".equals(city)
        -> "EXPRESS:" + id;
```

**A shallow branch, asking the domain directly:**

```java
case Order order when order.eligibleForExpress()
        -> "EXPRESS:" + order.id();
```

These two snippets are **illustrative case labels**, not standalone programs; the full class is in section 5.

The first snippet exposes the `Order → Customer → Address` details along with payment status, country, and city policies. It is useful when *the structural matching itself* is what the reader needs to see. But if the real question is "Is the order eligible for express delivery?", a name like `eligibleForExpress()` makes the intent clearer.

The key takeaway: **readability depends on the business question**, not on which form is shorter. Nested patterns are not wrong; they are simply not the best choice in every context.

### Signs you are using patterns as a code-shortening trick

- The reader has to count parentheses `(...)` to tell which variable belongs to which record.
- Variables are bound but never used, just because you tried to deconstruct the entire structure.
- Long guards mix business conditions with type-recognition logic.
- The same nested pattern is copied across multiple controllers or services.
- Adding a field to a record forces many callers to change, even though the business meaning has not changed.
- The `null` and fallback paths become hard to trace.
- One very long line replaces a few `if` lines with clear variable names.

These signs are **prompts to reconsider**, not mandatory rules to remove patterns.

## 3. Distinguish Three Responsibilities

| Responsibility | Question | Appropriate Tool |
|---|---|---|
| **Type classification** | Is the data an `Order`? | `input instanceof Order order` or `case Order order` |
| **Structural deconstruction** | Does the object have nested `Customer`/`Address` to extract components? | `Order(..., Customer(..., Address(...)), ...)` when needed |
| **Business rule** | Is the order eligible for express delivery? | `order.eligibleForExpress()` or a policy/domain service |

Patterns help **recognize and extract data**. Domain methods help **name the decision**. Mixing both in a single branch is not always wrong, but if it creates a hard-to-read expression, you should reduce the number of details exposed at the caller.

For example, do not force domain logic into a generically named helper like `Utils.check(...)` just to make a `switch` look short. A good method must be placed where its responsibility is clear and have a name that describes what is being decided.

## 4. Illustrative Problem and Behavioral Contract

Suppose we have four types:

```java
enum PaymentStatus { PAID, PENDING }

record Address(String city, String country) {}

record Customer(String name, Address address) {}

record Order(String id, Customer customer, PaymentStatus status) {}
```

These are **illustrative declarations** and do not need to be saved as separate files; the full program in section 5 defines them inside one class.

A **hypothetical policy for learning purposes**: an `Order` is tagged `EXPRESS` if:

1. Its payment status is `PAID`.
2. It has a non-`null` `Customer`.
3. It has a non-`null` `Address`.
4. The country is `VN` and the city is `HCM`.

Every other `Order` must return `STANDARD:<id>`; any input that is not an `Order` (including `null`) returns `NOT_ORDER`. This is the behavioral contract to preserve when changing how it is written.

### Approach A — dense nested pattern

```java
static String routeDense(Object input) {
    return switch (input) {
        case null -> "NOT_ORDER";
        case Order(var id,
                   Customer(var name, Address(var city, var country)),
                   var status)
                when status == PaymentStatus.PAID
                     && "VN".equals(country)
                     && "HCM".equals(city) -> "EXPRESS:" + id;
        case Order(var id, var customer, var status) -> "STANDARD:" + id;
        default -> "NOT_ORDER";
    };
}
```

**Pros:** explicitly reveals the structure required by the `EXPRESS` branch; the compiler handles matching the nested records. **Cons:** business logic and record structure are crammed into a single `case`; the `name` variable is bound but unused; domain changes require modifying the guard at the caller.

### Approach B — shallow `switch` with a domain method

```java
static String routeSwitch(Object input) {
    return switch (input) {
        case null -> "NOT_ORDER";
        case Order order when order.eligibleForExpress()
                -> "EXPRESS:" + order.id();
        case Order order -> "STANDARD:" + order.id();
        default -> "NOT_ORDER";
    };
}
```

**Pros:** clearly shows the two choices for `Order`. The reader does not need to know the internals of `Customer` or `Address`. This approach works well if there are genuinely multiple classification branches, or if `switch` expressions are used consistently across the codebase.

### Approach C — shallow type pattern with a guard clause

```java
static String routeReadable(Object input) {
    if (!(input instanceof Order order)) {
        return "NOT_ORDER";
    }
    return (order.eligibleForExpress() ? "EXPRESS:" : "STANDARD:")
            + order.id();
}
```

With only two states for `Order` in this problem, Approach C can be the **easiest to understand**: no `switch`, no repeated `Order` branch, and no deconstruction needed. The pattern variable `order` remains in scope after the `if` because if `instanceof` is false, the method has already returned (flow scoping). Both `null` input and wrong-type input return `NOT_ORDER`.

**There is no absolute "winner":** if more event types are added, the `switch` in Approach B may fit better. If you are handling a nested structure at a single boundary, the nested pattern in Approach A may be more direct. Decide based on **intent, depth, and number of branches**, not on having fewer characters.

## 5. Complete Java 21 Example: Three Ways of Writing, Same Behavior

Create the file **`PatternReadabilityDemo.java`** with the following content:

```java
import java.util.Objects;

public class PatternReadabilityDemo {
    enum PaymentStatus { PAID, PENDING }
    record Address(String city, String country) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer, PaymentStatus status) {
        boolean eligibleForExpress() {
            if (status != PaymentStatus.PAID || customer == null) {
                return false;
            }
            Address address = customer.address();
            return address != null
                    && "VN".equals(address.country())
                    && "HCM".equals(address.city());
        }
    }

    static String routeDense(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order(var id,
                       Customer(var name, Address(var city, var country)),
                       var status)
                    when status == PaymentStatus.PAID
                         && "VN".equals(country)
                         && "HCM".equals(city) -> "EXPRESS:" + id;
            case Order(var id, var customer, var status) -> "STANDARD:" + id;
            default -> "NOT_ORDER";
        };
    }

    static String routeSwitch(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order order when order.eligibleForExpress()
                    -> "EXPRESS:" + order.id();
            case Order order -> "STANDARD:" + order.id();
            default -> "NOT_ORDER";
        };
    }

    static String routeReadable(Object input) {
        if (!(input instanceof Order order)) {
            return "NOT_ORDER";
        }
        return (order.eligibleForExpress() ? "EXPRESS:" : "STANDARD:")
                + order.id();
    }

    static void check(String label, Object input, String expected) {
        String dense = routeDense(input);
        String guarded = routeSwitch(input);
        String simple = routeReadable(input);
        if (!Objects.equals(expected, dense)
                || !Objects.equals(dense, guarded)
                || !Objects.equals(guarded, simple)) {
            throw new AssertionError(label + ": " + dense + " / "
                    + guarded + " / " + simple + ", expected=" + expected);
        }
        System.out.println(label + " => " + simple);
    }

    public static void main(String[] args) {
        check("paid HCM", new Order("O1", new Customer("An",
                new Address("HCM", "VN")), PaymentStatus.PAID), "EXPRESS:O1");
        check("pending HCM", new Order("O2", new Customer("An",
                new Address("HCM", "VN")), PaymentStatus.PENDING), "STANDARD:O2");
        check("other city", new Order("O3", new Customer("An",
                new Address("HN", "VN")), PaymentStatus.PAID), "STANDARD:O3");
        check("other country", new Order("O4", new Customer("An",
                new Address("HCM", "US")), PaymentStatus.PAID), "STANDARD:O4");
        check("null customer", new Order("O5", null,
                PaymentStatus.PAID), "STANDARD:O5");
        check("null address", new Order("O6", new Customer("Binh", null),
                PaymentStatus.PAID), "STANDARD:O6");
        check("null city", new Order("O7", new Customer(null,
                new Address(null, "VN")), PaymentStatus.PAID), "STANDARD:O7");
        check("null country", new Order("O8", new Customer("Chi",
                new Address("HCM", null)), PaymentStatus.PAID), "STANDARD:O8");
        check("null status", new Order("O9", new Customer("Dung",
                new Address("HCM", "VN")), null), "STANDARD:O9");
        check("null id", new Order(null, new Customer("Em",
                new Address("HCM", "VN")), PaymentStatus.PAID), "EXPRESS:null");
        check("root null", null, "NOT_ORDER");
        check("wrong type", "text", "NOT_ORDER");
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 PatternReadabilityDemo.java
java PatternReadabilityDemo
```

**Verified stdout:**

```text
paid HCM => EXPRESS:O1
pending HCM => STANDARD:O2
other city => STANDARD:O3
other country => STANDARD:O4
null customer => STANDARD:O5
null address => STANDARD:O6
null city => STANDARD:O7
null country => STANDARD:O8
null status => STANDARD:O9
null id => EXPRESS:null
root null => NOT_ORDER
wrong type => NOT_ORDER
```

The `check(...)` method not only compares the three implementations against one another, but also against an independent `expected` value. If any implementation returns the wrong result, the program throws `AssertionError`. The example has been compiled with `javac --release 21` and run successfully for **12 scenarios**, including `null` at various levels and non-`Order` inputs. In a real codebase, you still need to test invariants and dependencies specific to the project's domain.

## 6. Why Do All Implementations Preserve Null Behavior?

This is where a shorter pattern can accidentally change the logic.

### 6.1. Non-null nested records

In Approach A:

```java
Order(var id,
      Customer(var name, Address(var city, var country)),
      var status)
```

This branch matches only if the `Order`, `Customer`, and `Address` objects all exist. `Customer(...)` or `Address(...)` **does not match when that record itself is `null`**. When it fails to match, `case Order(var id, var customer, var status)` handles it next and returns `STANDARD` for an `Order` with missing components.

In Approaches B and C, `eligibleForExpress()` achieves the same thing by checking:

```java
if (status != PaymentStatus.PAID || customer == null) {
    return false;
}
Address address = customer.address();
return address != null
        && "VN".equals(address.country())
        && "HCM".equals(address.city());
```

The snippet above **is the method body already present in the program in section 5**, not a standalone class. If you drop `customer == null` or `address != null` when moving logic into a method, the new version can throw `NullPointerException` and is no longer equivalent.

### 6.2. Leaf components can be null

The `city` and `country` components are `String`. The patterns `var city` and `var country` directly inside `Address(...)` can **bind `null`**. The guards `"HCM".equals(city)` and `"VN".equals(country)` remain safe, returning `false` when the argument is null.

The domain version uses `"VN".equals(address.country())` and `"HCM".equals(address.city())` to stay null-safe. Refactoring to `address.city().equals("HCM")` would fail on null city data. Being "concise" does not justify changing the outcome.

### 6.3. Root null and other types

`routeDense` and `routeSwitch` have `case null -> "NOT_ORDER"` and `default -> "NOT_ORDER"`. Do not assume that `default` in a pattern `switch` automatically catches a null selector.

`routeReadable` uses `input instanceof Order order`: this expression returns `false` if the root is null or of the wrong type, so the guard clause returns `NOT_ORDER` without needing a `case null` branch.

### 6.4. Unused variables and nullable IDs

In the nested pattern, `var name` is bound but never used to decide express eligibility. A reviewer might ask: "Why does the routing layer need to know the customer's name?" That suggests moving to a shallow type pattern.

All three versions handle `id == null` via string concatenation, producing `EXPRESS:null` when eligible. **This is behavior of the example, not a domain recommendation to allow missing IDs.** If non-null IDs are required, change that invariant separately rather than mixing it into a refactor.

## 7. Common Pitfalls When Trying to Use Patterns for Everything

### 7.1. Using switch for a simple true/false question

When the input already has type `Order` and you only need a boolean answer, the following usually adds little value:

```java
boolean eligible = switch (order) {
    case Order(var id, Customer(var name, Address(var city, var country)),
               var status)
            when status == PaymentStatus.PAID
                 && "VN".equals(country)
                 && "HCM".equals(city) -> true;
    default -> false;
};
```

**This is an illustrative snippet** using the records from section 5. If you only need "eligible or not", `order.eligibleForExpress()` states the question directly without deconstructing it yourself. If `order` can be null, you must define the method's contract clearly or handle null at the call boundary.

### 7.2. Making a pattern dense just to avoid a few accessor calls

For example, when you only need the order ID, a pattern like:

```java
case Order(var id, Customer(var name, Address(var city, var country)),
           var status) -> id;
```

accidentally requires `customer` and `address` to be non-null, even though the logic only wants `id`. It **changes the accepted set of values** and introduces an unrelated hidden condition.

If the selector is already classified as `Order`, using:

```java
case Order order -> order.id();
```

is clear and covers every `Order`, including those with null components. These are two **illustrative case labels** and must be placed inside an appropriate `switch`.

### 7.3. Overusing multiple pattern variables

Writing `Order(var id, var customer, var status)` does not mean you have to use all three variables. Still, if the logic only needs to ask one thing about `Order`, `case Order order` is often simpler. Conversely, if you genuinely need multiple components to build the output, deconstruction has a clear purpose.

### 7.4. Hiding business logic in a long guard

A long `when` clause with many `&&` and `||` operators forces the reader to infer the rule's name on their own. When a condition has its own meaning and is reused, consider a helper or domain method. Any extraction must **preserve grouping parentheses, evaluation order, and short-circuiting**: `a && (b || c)` is different from `a && b || c`.

### 7.5. Reordering cases because the new version looks cleaner

In a pattern `switch`:

```java
case Order order when order.eligibleForExpress() -> "EXPRESS";
case Order order -> "STANDARD";
```

the guarded branch must come **before** the general branch. Reversing them causes the narrower branch to be shadowed (*dominated case label*) and triggers a compile-time error. Focusing on shortening code while forgetting branch order can make a refactor invalid.

## 8. When Do Patterns Actually Make Code More Readable?

Do not conclude that "fewer patterns is always better." A pattern is useful when it **carries important structural information**:

- **Classifying a broadly typed variable:** `if (input instanceof Order order)` both checks the type and safely binds the variable, replacing a manual cast.
- **Handling multiple data variants:** a `switch` over a sealed hierarchy can express cases that the compiler checks for completeness; when no other cases are needed, exhaustiveness is a major benefit.
- **Deconstructing a record at a data boundary:** when you genuinely need several components of a record to produce a result, a pattern can avoid chains of accessors and casts.
- **Matching nested structure as a requirement:** if the logic applies only when a nested record actually exists, a nested record pattern expresses that condition clearly.

Example of a short, purposeful type pattern:

```java
static String label(Object input) {
    if (input instanceof String text) {
        return "Text length=" + text.length();
    }
    return "Not text";
}
```

This is a standalone illustrative method that can be placed in a Java class. There is no need for `String text = (String) input`, and using the pattern **reduces boilerplate without hurting readability**.

A pattern is worth using only when it helps the reader answer: **"What shape must the input have for this branch to be valid?"** If the real question is "Which business rule applies?", a named domain method usually communicates it better.

## 9. Readability Evaluation Criteria

Instead of counting lines, ask yourself:

| Criterion | Review Question |
|---|---|
| **Intent** | Can you tell what the branch returns without decoding every component? |
| **Depth** | Does the caller have to know 3–4 levels of records? |
| **Scope** | Are pattern variables clearly named and used in the right places? |
| **Null contract** | Are nested nulls and leaf nulls easy to predict? |
| **Fallback** | Where do non-matching inputs go, and is that easy to see? |
| **Policy isolation** | When a rule changes, do you edit one place or many callers? |
| **Testability** | Can the rule be tested on its own, or must you construct a complex switch? |
| **Stability** | When record structure changes, do places that only care about business logic have to change? |
| **Cognitive load** | How many conditions must a reader hold in mind to understand one branch? |

The hardest thing to measure is *fit for purpose* (local clarity): a long pattern may be reasonable in a single mapper, yet cause coupling in a business service. The context of the code matters more than a fixed style preference.

## 10. Refactor Step by Step Instead of Rewriting Everything at Once

1. **Pin down existing behavior:** list inputs/nulls/boundaries and expected results. If the old code has a bug, do not silently change the bug during a syntax refactor; keep behavior-fix decisions separate.
2. **Separate structure from business logic:** `input instanceof Order` is a type check; `eligibleForExpress()` is a decision.
3. **Choose the shallowest pattern that suffices:** only deconstruct components used by the logic at the caller.
4. **Place domain methods in the right spot:** if it belongs to Order's behavior, consider `Order.eligibleForExpress()`; if it depends on shipping-zone policies from an external system, consider a policy/service with explicit dependencies.
5. **Preserve ordering and null contracts:** when moving from a nested record pattern to a shallow type pattern, the helper must handle any components that may be null.
6. **Write before/after tests with independent expected values:** include wrong-type input, root null, nested null, leaf null, and true/false conditions.
7. **Read the diff as a reviewer:** which parts only change syntax, and which might alter input paths? Was any fallback branch lost?
8. **Evaluate the new version from a reader's perspective:** if you cannot state the method's purpose in one sentence, the pattern is still too dense or responsibilities are not well separated.

You do not need to put every helper into a giant `Utils` class, nor split code into dozens of tiny methods just to make each `when` clause one word long. The level of abstraction should **reduce what needs to be understood**, not just shorten the caller.

## 11. Common Review Mistakes

| Mistake | Consequence | How to Avoid |
|---|---|---|
| Measuring only before/after line count | Mistakenly judging a short but cryptic expression as better | Compare intent, scope, fallback, and null handling |
| Using a nested record pattern when only an ID is needed | Introduces a hidden non-null condition | Use `case Order order` or `order.id()` |
| Shortening by removing a fallback branch | Changes behavior for missing components | Map out input paths before and after |
| Moving to a domain method but forgetting null checks | May introduce a `NullPointerException` | Compare against nested record pattern semantics |
| Packing many conditions into `when` | Rule is hard to name, easy to copy-paste and drift | Extract a predicate/domain method when meaningful |
| Refactoring `constant.equals(value)` into `value.equals(constant)` | Fails on null values | Keep null-safe comparisons |
| Swapping the order of guarded and general branches | Dominated case or changes which branch is chosen | Keep specific branches before broader ones |
| Creating one-line helpers for every tiny operation | Readers have to jump across many classes/methods | Extract only by named responsibility |
| Mixing performance optimization with readability refactoring | Hard to isolate the cause of behavior changes | Measure performance and separate targeted changes |

## 12. Practice: Choosing the More Readable Expression

**Scenario A.** The input is `Object`; you only need to print its length when it is a `String`.

- Using `instanceof String text` is natural: the type pattern eliminates the cast without introducing structural complexity.
- There is no need for a multi-branch `switch` if there is only one input type and one fallback.

**Scenario B.** The input is `Order`; the business question is "is it eligible for express delivery?".

- Prefer `order.eligibleForExpress()` or a named policy if the rule belongs to the domain.
- Avoid deconstructing every component at every caller just to re-evaluate the same rule.

**Scenario C.** The input is an event type with multiple variants, each requiring a different structure.

- A `switch` with type/record patterns can reflect the set of cases well.
- If using a sealed hierarchy, consider exhaustiveness and branch ordering.
- A nested record pattern should only be as deep as needed for that branch's behavior.

**Scenario D.** You already have a `Customer` and want `address.city()`.

- Direct accessors are usually clearer than a long `instanceof` record pattern.
- If `address` can be null, handle it according to an explicit contract rather than using a pattern to hide the null check.

### Self-Check Questions

1. Why can `case Order order` be clearer than `case Order(var id, Customer(var name, Address(...)), var status)`? **Because the caller only needs a named Order, not knowledge of the entire structure and policy.**
2. Does the nested record pattern `Customer(...)` match when `customer` is null? **No.** If you switch to `Order order`, the domain method must handle that case.
3. Why can `String city`/`var city` directly on a component still bind null? **Because reference components of a record can be null; the existence of the record does not guarantee non-null leaf components.**
4. Should you avoid `instanceof String text` completely just to avoid patterns? **No.** It is a type pattern that usually makes intent clearer than a manual cast.
5. If two versions produce the same output across 12 cases, does that prove they are equivalent for all inputs? **No.** It is regression evidence for the tested data; you still need to examine the domain contract and add tests.
6. When is `switch` better than a simple guard clause? **When there are multiple independent choices/data variants, or when exhaustiveness clarifies which cases must be handled.**
7. Should you prefer a long nested pattern just because it is shorter than 4 lines of `if`? **No.** The criteria are readability, scope of responsibility, and branch semantics.

## Conclusion

**Do not use patterns just to shorten code.** Use them when type classification or structural deconstruction helps express intent. For business rules, a clearly named method usually keeps callers less coupled to structure. The best style to choose is the one that highlights **meaningful conditions**, keeps `null` and fallback cases easy to follow, and preserves behavior.

In Java 21, nested record patterns, `switch` guards, and type patterns are useful tools; design quality lies in choosing **the right level of abstraction**, not cramming every possible syntax feature onto a single line.

## Official References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java Language Specification SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
