# Refactoring a Nested Pattern into a Domain Method (Java 21)

## Objectives

After this lesson, you will know how to recognize when a `nested record pattern` contains a **business rule**, move that rule into a method whose name expresses its meaning in the domain, and preserve behavior regarding types, `null`, `switch` branch ordering, and `when` conditions. This lesson uses **Record Patterns (JEP 440)** and **Pattern Matching for switch (JEP 441)**, which have been standard features since Java 21.

**Key principle:** pattern matching is well suited for **identifying and decomposing data structures**; domain methods are well suited for **expressing business decisions**. Refactoring is valuable when multiple places must understand the details of a record's structure just to answer a single business question.

## 1. The Problem: Business Conditions Embedded in Structure

Suppose the example application has three nested records:

```text
Order
├── id: String
├── payment: PaymentState
└── customer: Customer
    ├── name: String
    └── address: Address
        ├── city: String
        └── country: String
```

This is a **hypothetical rule for the example**, not a real-world shipping policy: an order qualifies for same-day delivery when it is paid (`PAID`), the country code is `VN`, and the city code is `HCM`. The object may be missing `customer` or `address`; when missing, the order does not qualify.

A direct way to write this in the orchestration layer:

```java
case Order(
        var id,
        Customer(var name, Address(var city, var country)),
        var payment)
        when payment == PaymentState.PAID
             && "VN".equals(country)
             && "HCM".equals(city) -> "SAME_DAY";
```

**This is an illustrative `case` branch**, which must be placed inside an appropriate `switch`. It is valid in Java 21, but it carries costs when repeated across controllers, services, or event handlers:

- Every call site must know `Order → Customer → Address`, even when the goal is only to ask "does this order qualify for same-day delivery?".
- The codes `"VN"` and `"HCM"` along with the payment rule are scattered. Policy changes can easily cause different places to drift out of sync.
- A structural change, such as moving the shipping address to be a direct component of `Order`, can require updating many patterns.
- Cases where `customer == null`, `address == null`, or leaf values are `null` are easily handled inconsistently.

The pattern is **not wrong**; what needs consideration is whether the business rule is being placed in too many locations.

## 2. Choosing Domain Methods and Where to Place Responsibility

Instead of letting clients decide from record components, convert the logic into named questions:

| Domain Type | Method | Responsibility |
|---|---|---|
| `Address` | `supportsSameDay()` | Is the address within the same-day delivery area according to the example policy? |
| `Customer` | `hasSameDayAddress()` | Does the customer have a qualifying address? |
| `Order` | `qualifiesForSameDay()` | Is the order paid and does it have a customer with a qualifying address? |

After refactoring, the client only needs to ask:

```java
case Order order when order.qualifiesForSameDay() -> "SAME_DAY";
```

This is a **domain method**, because it expresses a rule about `Order` and uses components belonging to the domain itself. It does not depend on HTTP, a database, the UI, or a response format.

Place the method on the class that has sufficient context to answer the question and owns the rule. For an order rule, `Order` is the appropriate entry point; `Address` and `Customer` only hold checks that make sense on their own. If the policy depends on pricing, limits, time zones, or configuration that changes frequently from external services, consider an **injected domain service/policy object** rather than hiding external service access inside a getter or record.

## 3. Complete Example: Before and After Refactoring

Create a file named **`NestedPatternRefactorDemo.java`** with the following full contents. Both `routeBefore` and `routeAfter` return three values: `SAME_DAY`, `STANDARD`, and `NOT_ORDER`.

```java
public class NestedPatternRefactorDemo {
    enum PaymentState { PAID, PENDING }

    record Address(String city, String country) {
        boolean supportsSameDay() {
            return "VN".equals(country) && "HCM".equals(city);
        }
    }

    record Customer(String name, Address address) {
        boolean hasSameDayAddress() {
            return address != null && address.supportsSameDay();
        }
    }

    record Order(String id, Customer customer, PaymentState payment) {
        boolean qualifiesForSameDay() {
            return payment == PaymentState.PAID
                    && customer != null
                    && customer.hasSameDayAddress();
        }
    }

    // BEFORE: the client knows the entire Order -> Customer -> Address structure.
    static String routeBefore(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order(var id,
                       Customer(var name, Address(var city, var country)),
                       var payment)
                    when payment == PaymentState.PAID
                         && "VN".equals(country)
                         && "HCM".equals(city) -> "SAME_DAY";
            case Order(var id, var customer, var payment) -> "STANDARD";
            default -> "NOT_ORDER";
        };
    }

    // AFTER: the client only needs the Order type and a business-meaningful question.
    static String routeAfter(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order order when order.qualifiesForSameDay() -> "SAME_DAY";
            case Order order -> "STANDARD";
            default -> "NOT_ORDER";
        };
    }

    // Regression check: every case must produce the same result.
    static void show(String label, Object input) {
        String before = routeBefore(input);
        String after = routeAfter(input);
        if (!before.equals(after)) {
            throw new AssertionError(label + ": before=" + before + ", after=" + after);
        }
        System.out.println(label + ": " + after);
    }

    public static void main(String[] args) {
        show("null root", null);
        show("other type", "text");
        show("paid HCM", new Order("O1", new Customer("An",
                new Address("HCM", "VN")), PaymentState.PAID));
        show("pending HCM", new Order("O2", new Customer("An",
                new Address("HCM", "VN")), PaymentState.PENDING));
        show("no customer", new Order("O3", null, PaymentState.PAID));
        show("no address", new Order("O4", new Customer("An", null),
                PaymentState.PAID));
        show("null city", new Order("O5", new Customer("An",
                new Address(null, "VN")), PaymentState.PAID));
        show("different city", new Order("O6", new Customer("An",
                new Address("HN", "VN")), PaymentState.PAID));
        show("null payment", new Order("O7", new Customer("An",
                new Address("HCM", "VN")), null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 NestedPatternRefactorDemo.java
java NestedPatternRefactorDemo
```

Output:

```text
null root: NOT_ORDER
other type: NOT_ORDER
paid HCM: SAME_DAY
pending HCM: STANDARD
no customer: STANDARD
no address: STANDARD
null city: STANDARD
different city: STANDARD
null payment: STANDARD
```

The example has been verified to compile with `javac --release 21` and run. In each case, `show` compares the **before/after** results and throws `AssertionError` if they differ. This is a behavioral check for the sample data; in a real project, unit tests for edge cases according to the business contract are still needed.

## 4. Why Does the Refactoring Preserve Behavior?

### 4.1. Null Root and Non-Order Values

In both `routeBefore` and `routeAfter`, `case null` returns `NOT_ORDER`. If the selector is a `String`, `default` also returns `NOT_ORDER`. The domain method is only called after `case Order order` has matched; it does not accept an arbitrary selector or handle casting itself.

Note: in a Java 21 pattern `switch`, writing `default` alone does not automatically catch a `null` selector. To preserve the problem's semantics, both versions explicitly declare `case null`.

### 4.2. Null Nested Records

In the before version, the `Customer(..., Address(...))` part only matches when both `Customer` and `Address` are **non-`null`** record instances. If either is `null`, the same-day branch does not match; the `case Order(var id, var customer, var payment)` branch receives the remaining `Order` and returns `STANDARD`.

In the after version, `Order.qualifiesForSameDay()` checks `customer != null`; `Customer.hasSameDayAddress()` checks `address != null` before accessing the next method. The `&&` operator in Java evaluates from left to right and short-circuits immediately upon encountering `false`. Both paths therefore return `STANDARD` without dereferencing a missing object.

### 4.3. Null Leaf Components

`Address(var city, var country)` is a record pattern that requires a non-`null` `Address`. However, the patterns `var city` and `var country` **can bind `null`** from reference-typed components. The conditions `"HCM".equals(city)` and `"VN".equals(country)` evaluate to `false` when the argument is `null`.

The domain version continues to use `constant.equals(component)`. Both still treat `city == null` or `country == null` as not qualifying. The comparison `payment == PaymentState.PAID` is also safe if `payment == null`.

**Do not arbitrarily replace `"HCM".equals(city)` with `city.equals("HCM")`** when refactoring: if `city` can be null, the second form throws `NullPointerException` and changes the behavioral contract.

### 4.4. Switch Ordering and Dominance

In the after version:

```java
case Order order when order.qualifiesForSameDay() -> "SAME_DAY";
case Order order -> "STANDARD";
```

The branch with `when` must come before the general `Order order` branch. If the order is reversed, the general branch covers the narrower branch and the compiler reports a **dominated case label** error. A `when` guard only runs after its corresponding pattern has matched.

Before refactoring, the specific nested branch also had to precede the broader `Order(...)` branch. Refactoring does not allow arbitrarily changing the order of `case` labels.

## 5. Safe Refactoring Steps in a Codebase

1. **Pin down the exact current behavior.** Record the input types, `null` branches, default values, guards, `case` ordering, and outputs that must be preserved. Do not mix refactoring with business requirement changes.
2. **Name the business question.** If the expression means "does the order qualify for same-day delivery?", a name like `qualifiesForSameDay()` is clearer than `check()`, `isValid()`, or `isMatch()`.
3. **Choose where the rule belongs.** `Order` is responsible for checking payment and the customer; `Customer` checks for the existence of the address; `Address` checks the same-day delivery area. Do not move code just to increase the number of methods.
4. **Move the logic while preserving the null contract.** Each step must preserve short-circuiting and branching conditions. If rejecting `null` in a constructor is needed, that is a separate domain change requiring evaluation, not a pure refactoring.
5. **Replace the nested pattern at the caller with a shallow pattern.** Go from `Order(Customer(Address(...)), ...)` to `Order order when order.qualifiesForSameDay()`; or if the input already has type `Order`, call `order.qualifiesForSameDay()` directly.
6. **Run regression checks using a state table.** Cover qualifying cases, non-qualifying cases, wrong types, null root, and null at each level. Compare before/after results before removing the old code in production.

Only remove the old expression from production once all callers use the new rule and all edge cases have been verified.

## 6. When Should You Still Use a Nested Pattern?

Not every nested record pattern needs to be extracted into a domain method.

**Keep the pattern at the call site** when the task is a one-off mapping from a data structure to a result, such as unpacking an event, logging data, or selecting a display format. The following example only extracts the city name from an `Order` if the structure exists:

```java
static String cityForDisplay(Object input) {
    return switch (input) {
        case Order(var id, Customer(var name, Address(var city, var country)),
                   var payment) -> city == null ? "(unknown)" : city;
        case null, default -> "(no address)";
    };
}
```

This is an **illustrative method** to add to the `NestedPatternRefactorDemo` class in section 3. The decomposition is only for displaying a value and does not necessarily represent a reusable domain rule.

**Prefer a domain method** when the expression represents a named business decision, appears in multiple places, or needs to remain stable when internal data structures change. The caller should then ask the domain about behavior rather than knowing every component.

**Consider a domain service/policy** when the rule requires data from outside the aggregate: time-based configuration, delivery zones updated from another system, operating schedules, pricing, or permissions. Do not silently add a network call inside `supportsSameDay()` just to keep the syntax readable.

## 7. Notes on Records, APIs, and Performance

- **Records do not forbid null by default.** Reference components can receive `null` unless a constructor or system contract specifies otherwise. The null policy belongs to the domain and must be preserved when refactoring.
- **Records are shallowly immutable.** Each component cannot be reassigned after initialization, but a referenced object inside can still be mutable. Check methods should avoid mutating state.
- **Domain methods should have clear, consistent results.** A predicate like `qualifiesForSameDay()` works well when the result does not depend on side effects; if the decision requires a point in time, pass a `Clock` or an `Instant` input rather than implicitly reading system time.
- **Do not expose `Object` if the domain API already knows the type.** `qualifiesForSameDay()` lives on `Order`, so it does not need an `Object` parameter or `instanceof` inside itself. `instanceof` or `switch` only remains at the boundary where objects must be classified.
- **Do not assume the new method is always faster.** The main benefits of refactoring are consistency and reduced structural coupling. Performance depends on the JVM/JIT and workload; only optimize after measuring.
- **Method names must reflect the policy.** `supportsSameDay()` in the example simulates a static set of codes; if the same-day delivery policy varies by date, use a name and API that reflect the required data.

A shorter version at the boundary when only a boolean is needed:

```java
static boolean eligible(Object input) {
    return input instanceof Order order && order.qualifiesForSameDay();
}
```

The snippet above uses a type pattern to confirm the input is an `Order`; the business logic is still decided by the domain. When `input == null`, `instanceof` evaluates to `false` and the method is not called.

## 8. Common Refactoring Mistakes

| Mistake | Impact | How to Avoid |
|---|---|---|
| Turning a nested pattern into an accessor chain without null checks | `NullPointerException` when `customer`/`address` is missing | Keep short-circuiting on each component |
| Reordering broad/narrow `case` branches | Dominated case error, or different branch selected | Keep ordering from specific to general |
| Omitting `case null` | A null selector may throw `NullPointerException` | Explicitly document and handle `null` at the boundary |
| Changing `constant.equals(value)` to `value.equals(constant)` | Changes behavior for nullable leaves | Keep null-safe comparisons |
| Moving the rule into a controller or generic `Utils` helper | Rule remains scattered, lacks ownership | Give it a meaningful name on the domain or domain policy |
| Adding `requireNonNull` to constructors in the same refactoring | Changes what data can be constructed | Separate invariant tightening into its own change |
| Putting I/O, database calls, or wall-clock time into a predicate | Behavior becomes hard to test and unpredictable | Pass required context/policy or use a domain service |
| Extracting too many methods for a one-off expression | Makes code harder to follow | Evaluate business meaning and reuse |

## 9. Self-Check

Suppose the input is `new Order("O8", new Customer("Binh", null), PaymentState.PAID)`:

1. Does the `Order(Customer(Address(...)), ...)` branch match? **No**: `Address(...)` does not match `null`, even though `Order` and `Customer` are present.
2. Does `case Order order when order.qualifiesForSameDay()` enter `SAME_DAY`? **No**: `hasSameDayAddress()` returns `false`.
3. Which branch handles it next? **`case Order order -> "STANDARD"`**, because `Order` is present and does not satisfy the guard.
4. If `country` changes to `null` while `city` remains `"HCM"`, does the result change? **No**: `"VN".equals(null)` is `false` in both versions.
5. If you add `order.id() != null` to `qualifiesForSameDay()` when it was not in the old logic, is it still a behavior-preserving refactoring? **No**: that is a business rule change that needs separate review and testing.

## Key Takeaways

- A **nested record pattern** expresses *which structure is present*.
- A **domain method** expresses *which business rule is satisfied*.
- When migrating from `case Order(Customer(Address(...))) when ...` to `case Order order when order.qualifiesForSameDay()`, preserve behavior for `null`, branch ordering, guards, and default results.
- Good refactoring reduces how much callers need to know about internal structure and keeps rules in a single place with clear ownership, without changing observable inputs/outputs.

## Official Documentation

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
