# Extensible Switch Structures in Java 21

## 1. Goal: Extending Behavior Without Losing Control of the Switch

A `switch` that starts with two or three cases is usually easy to read. However, as business requirements add more variants, priority conditions, `null` handling, or integrations with multiple services, a `switch` can become a hotspot where too many changes concentrate.

An **extensible switch structure** is an organization where a maintainer can:

- Look at the `case` list to understand the existing data variants.
- Know where to update when adding a new variant.
- Rely on the compiler to detect missing branches when working with a **closed set of variants**.
- Add special conditions without accidentally shadowing the general case.
- Separate **branch selection** from **long business logic**.
- Test each variant, the `null` policy, and condition thresholds.

In Java 21, the right tools include **pattern matching for switch** (JEP 441), **record patterns** (JEP 440), **sealed types**, `switch` expressions, `when` guards, and arrow-style switch rules (`->`).

Conceptual example:

```java
return switch (event) {
    case OrderCreated(var orderId, var customerId) -> ...;
    case PaymentCaptured(var orderId, var amountVnd) -> ...;
    case OrderCancelled(var orderId, var reason) -> ...;
};
```

This is a **syntax snippet** to show how branches are split by domain variant; `...` is not a valid Java expression. In the runnable program below, the branches return real values and all types are fully declared.

**Key point:** using pattern `switch` does not automatically make a design extensible. Maintainability depends on the **selector type**, **branch coverage rules**, **case ordering**, **separation of responsibilities**, and **testing**.

## 2. Identifying the Components of a Switch Pattern

| Component | Sample Syntax | Role |
| --- | --- | --- |
| Switch expression | `String message = switch (event) { ... };` | Transforms an input value into a result |
| Switch statement | `switch (event) { case ... -> handle(); }` | Dispatches actions |
| Type pattern | `case PaymentCaptured payment ->` | Checks the subtype and binds the whole object |
| Record pattern | `case PaymentCaptured(var id, var amount) ->` | Checks the record and deconstructs its components |
| Guard | `case PaymentCaptured(var id, var amount) when amount > 0 ->` | Adds a condition after the pattern has matched |
| Null label | `case null ->` | Specifies how a `null` selector is handled |
| Default label | `default ->` | Fallback for other values without a matching branch |
| Sealed hierarchy | `sealed interface Event permits A, B` | Restricts the allowed set of subtypes |

`when` is a **guard**, not a new kind of pattern. `case null` and `default` are labels, not type/record patterns. Variables such as `amount` or `id` in a pattern are only in scope where Java proves the match has succeeded.

## 3. Structuring the Domain with Sealed Interfaces and Records

Suppose a system needs to react to three kinds of order events:

```java
sealed interface OrderEvent
        permits OrderCreated, PaymentCaptured, OrderCancelled {}

record OrderCreated(String orderId, String customerId)
        implements OrderEvent {}

record PaymentCaptured(String orderId, long amountVnd)
        implements OrderEvent {}

record OrderCancelled(String orderId, String reason)
        implements OrderEvent {}
```

This is a **declaration snippet** that can be placed in a source file at an appropriate scope. The complete program section below places them as nested declarations of a class.

Each variant explicitly states its own data:

- `OrderCreated`: order ID and customer ID.
- `PaymentCaptured`: order ID and captured amount in VND.
- `OrderCancelled`: order ID and cancellation reason.

`sealed` restricts the direct subtypes of `OrderEvent`. The `record` types are `final`, so the example forms a **closed set of variants** suitable for compiler exhaustiveness checking.

This is an important premise: if the selector only has type `Object`, the compiler cannot know that your domain has only three variants. If the selector has static type `OrderEvent`, the allowed set of subtypes is already expressed in the model.

### 3.1. A Switch Expression Handling All Subtypes

```java
static String code(OrderEvent event) {
    return switch (event) {
        case OrderCreated created -> "CREATED";
        case PaymentCaptured payment -> "CAPTURED";
        case OrderCancelled cancelled -> "CANCELLED";
    };
}
```

Each branch matches one permitted subtype. For the `OrderEvent` type, this is an **exhaustive** `switch` expression—no `default` is needed.

**Note on `null`:** the three type patterns above do not match `null`. Calling the switch with a `null` selector without explicit handling can throw a `NullPointerException`. Subtype exhaustiveness does not mean `null` is handled automatically.

If `null` is a valid API input:

```java
static String codeOrMissing(OrderEvent event) {
    return switch (event) {
        case null -> "MISSING";
        case OrderCreated created -> "CREATED";
        case PaymentCaptured payment -> "CAPTURED";
        case OrderCancelled cancelled -> "CANCELLED";
    };
}
```

On the other hand, if `null` is a programming error, you can use `Objects.requireNonNull(event)` before the switch instead of turning the error into a normal status.

## 4. Omitting `default` When You Want the Compiler to Flag New Subtypes

For a **closed domain** where every subtype needs its own handling, do not add `default` just to make the code always compile.

Suppose tomorrow a new variant appears:

```java
record OrderReturned(String orderId, String reason)
        implements OrderEvent {}
```

And the `permits` list of `OrderEvent` is updated to allow `OrderReturned`. When recompiling modules against the new hierarchy, a switch expression with only the three old cases will be flagged by the compiler to handle all cases. That is a positive maintenance signal.

If the switch has:

```java
default -> "OTHER";
```

then the new subtype can be silently routed into the generic branch. This may be unacceptable when the new behavior requires updating auditing, billing, notifications, or authorization.

**Practical guidelines:**

- **Closed domain:** handle each subtype explicitly; prefer an exhaustive switch without `default` when you need to ensure no variant is missed.
- **Open domain:** `default` is useful for expressing a policy for unsupported data.
- **From external data:** usually validate and convert to the domain model first; do not pass `Object` throughout the core business logic.

Here are two contrasting examples:

```java
// Closed domain (example snippet):
switch (event) {
    case OrderCreated created -> handleCreated(created);
    case PaymentCaptured payment -> handlePayment(payment);
    case OrderCancelled cancelled -> handleCancelled(cancelled);
}

// Open input (example snippet):
switch (payload) {
    case null -> handleMissing();
    case String text -> handleText(text);
    case byte[] bytes -> handleBytes(bytes);
    default -> handleUnsupported(payload);
}
```

The `handle...` methods are **illustrative business placeholders**, not a standalone runnable program; the actual methods must be defined. The important difference here is the branch coverage policy, not the method names.

### 4.1. Limits of Exhaustiveness Under Runtime Version Mismatch

The compiler checks against the types it knows **at compile time**. If a library containing a sealed hierarchy is updated independently after the switch code has been compiled, at runtime the code may encounter a new subtype that the old code does not recognize. In Java 21, an exhaustive switch that finds no matching branch under such unusual compatibility circumstances can throw `MatchException`.

Therefore, exhaustive checking **does not replace** recompiling related modules, integration testing, and version management during deployment.

## 5. Record Patterns Let Cases Show the Data They Use

When a branch only needs the components of a record, a record pattern lets the reader immediately see the inputs:

```java
static String describe(OrderEvent event) {
    return switch (event) {
        case null -> "missing event";
        case OrderCreated(var orderId, var customerId) ->
            "created " + orderId + " for " + customerId;
        case PaymentCaptured(var orderId, var amountVnd) ->
            "paid " + orderId + ": " + amountVnd + " VND";
        case OrderCancelled(var orderId, var reason) ->
            "cancelled " + orderId + ": " + reason;
    };
}
```

`OrderCreated(var orderId, var customerId)` is a **record pattern**. Java extracts components by the record's **declaration order**, not by the variable names `orderId` or `customerId`. Naming variables to match the domain helps prevent confusion when multiple components share the `String` type.

When you only need to classify the subtype and **do not need its components**, a type pattern can be simpler:

```java
case OrderCreated created -> "CREATED"
```

Do not mechanically deconstruct the entire record if the branch does not use those values. The goal is to convey just enough information for maintainability.

### 5.1. When Nested Patterns Start Becoming Hard to Read

If the data has deeply nested records, a long pattern can be useful for extracting the exact components:

```java
record Customer(String id, String displayName) {}
record Delivery(Customer customer, String trackingCode) {}

// Illustrative expression snippet:
if (value instanceof Delivery(
        Customer(var customerId, var customerName),
        var trackingCode)) {
    System.out.println(customerName + ": " + trackingCode);
}
```

However, when a nested record pattern makes a case span dozens of lines, consider binding the whole `Delivery delivery` object and passing it to a clearly named helper method. An extensible structure balances **visibility of the needed data** with **conciseness of the switch**.

## 6. `when` Guards: Extending Cases Without Losing the General Branch

Business logic may need to distinguish transactions of `1_000_000` VND or more:

```java
static String paymentLabel(OrderEvent event) {
    return switch (event) {
        case null -> "missing";
        case PaymentCaptured(var orderId, var amountVnd)
                when amountVnd >= 1_000_000L ->
            "large payment " + orderId;
        case PaymentCaptured(var orderId, var amountVnd) ->
            "payment " + orderId + ": " + amountVnd + " VND";
        case OrderCreated created -> "order created";
        case OrderCancelled cancelled -> "order cancelled";
    };
}
```

**Selection flow:**

1. Java tests the `PaymentCaptured(...)` pattern.
2. If it matches, the guard `amountVnd >= 1_000_000L` is evaluated.
3. If the guard is true, the `large payment` branch is chosen.
4. If the guard is false, the general `PaymentCaptured(...)` branch below can still receive the event.

`when` is not a new pattern; it is the conditional part of the `case` label. `amountVnd` is a pattern variable scoped to the guard and the corresponding branch.

### 6.1. Dominance: Putting a Broad Branch Before a Narrow One Causes an Error

**Code snippet intentionally fails to compile:**

```java
return switch (event) {
    case PaymentCaptured(var id, var amount) -> "payment";
    case PaymentCaptured(var id, var amount)
            when amount >= 1_000_000L -> "large payment"; // Dominated
    default -> "other";
};
```

The first branch already covers **every** `PaymentCaptured`. The second branch can never execute and is rejected by the compiler under the **dominance** rule.

Fix: guarded or more specific branches come first, followed by the general branch. This is an essential maintenance rule whenever adding a new case.

### 6.2. Boundary Values and Overlapping Guards

When there are multiple tiers:

```java
case PaymentCaptured(var id, var amount)
        when amount >= 5_000_000L -> "VIP";
case PaymentCaptured(var id, var amount)
        when amount >= 1_000_000L -> "LARGE";
case PaymentCaptured(var id, var amount) -> "STANDARD";
```

place the highest-priority tier first, lower tiers after, and the general branch last. If the two guards are swapped, amounts over 5 million will fall into the `LARGE` branch.

The compiler does not prove the mathematical meaning or disjointness of `when` conditions; you must **test boundary values**.

## 7. Switch Expressions and Switch Statements Serve Different Roles

Choose the construct based on whether you need a **result value** or **side effects**.

### 7.1. Use a Switch Expression to Return a Value

```java
static String eventType(OrderEvent event) {
    return switch (event) {
        case null -> "MISSING";
        case OrderCreated created -> "CREATED";
        case PaymentCaptured payment -> "PAYMENT";
        case OrderCancelled cancelled -> "CANCELLED";
    };
}
```

Advantage: a single expression with a definite result, without declaring `String result = ""` and assigning to it multiple times. With a sealed hierarchy, the compiler helps verify that no branch is missing. A switch expression forces every valid path to produce a result or throw an exception.

### 7.2. Use a Switch Statement to Dispatch Handlers

```java
// CODE SNIPPET: handler methods defined in the application
switch (event) {
    case null -> rejectMissingEvent();
    case OrderCreated created -> processCreated(created);
    case PaymentCaptured payment -> processPayment(payment);
    case OrderCancelled cancelled -> processCancelled(cancelled);
}
```

Advantage: looking at one place tells you which event is routed to which handler. Database updates, sending notifications, and policy checks should live in clearly named methods rather than being crammed into the same `case`.

A switch statement using patterns also follows enhanced-switch coverage rules; however, when producing a classification result, a switch expression is usually the more suitable structure.

### 7.3. Arrow Rules Prevent Accidental Fall-Through

The legacy switch form using `case ...:` can fall through into the next branch if `break` is forgotten:

```java
switch (kind) {
    case 1:
        System.out.println("one");
        break;
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
```

With `case 1 -> ...` and `case 2 -> ...`, each rule does not fall through into the next rule. As more branches are added, arrow rules usually make branching intent much clearer.

## 8. Multi-Line Branches: Use `yield`, Don't Turn the Switch into a Giant Block

A switch expression uses `yield` to produce a value when a case requires a multi-statement block:

```java
static String formatted(OrderEvent event) {
    return switch (event) {
        case null -> "missing";
        case OrderCreated(var orderId, var customerId) -> {
            String prefix = "Order " + orderId;
            yield prefix + " belongs to " + customerId;
        }
        case PaymentCaptured(var orderId, var amountVnd) ->
            "Paid " + orderId + ": " + amountVnd + " VND";
        case OrderCancelled(var orderId, var reason) ->
            "Cancelled " + orderId + ": " + reason;
    };
}
```

Inside a switch expression block, `yield value;` produces the value for the switch. Do not use `break value;` as in some older experimental syntax. Outside, `return switch (...) { ... };` returns the value of the switch expression from the method.

**Design note:** a huge block of dozens of lines doing DB queries, sending emails, mutating state, and formatting strings will be very hard to extend even if `yield` is used correctly. Extract the logic:

```java
// CODE SNIPPET illustrating structure; formatting functions must be implemented:
return switch (event) {
    case null -> "missing";
    case OrderCreated created -> formatCreated(created);
    case PaymentCaptured payment -> formatPayment(payment);
    case OrderCancelled cancelled -> formatCancelled(cancelled);
};
```

Each handler can be tested independently; the switch only decides the **route**.

## 9. Null Policy, Fallbacks, and Selector Types

There is no single `null` policy that fits every system.

| Case | Expression to Consider |
| --- | --- |
| `null` represents an expected missing event | `case null -> "missing"` |
| `null` is an API contract violation | `Objects.requireNonNull(event)` before the switch |
| Source is an external `Object` | `case null` and `default` have clear meanings |
| Source is a closed sealed domain | Handle every subtype and consider omitting `default` |

Open-type data example:

```java
static String accept(Object payload) {
    return switch (payload) {
        case null -> "MISSING";
        case String text -> "TEXT";
        case byte[] bytes -> "BINARY";
        default -> "UNSUPPORTED";
    };
}
```

Here `Object` can hold countless types, so `default` means **reject unsupported types**. It is not a substitute for `case null`; a switch without proper `null` handling can throw a `NullPointerException`.

Do not always return `"unknown"` for `null` just so the program "doesn't error." In critical transaction domains, a missing event may require an exception or an explicit rejection result.

### 9.1. A Sealed Interface Is Not Necessarily a Closed Set of Leaves

A permitted subtype can be `non-sealed`, allowing other subclasses to appear. If the domain is partially open, handling a few concrete subtypes may not cover every runtime object. You may need a broader type pattern in the appropriate place or a change to the model.

For typical domain events, a sealed interface + `final` record subtypes keep the set of variants closed and clear.

## 10. Extending by Changing the Domain Once and Reviewing Related Switches

Workflow when adding `OrderReturned` to a system with three event types:

1. **Define the subtype** and its appropriate components, such as `record OrderReturned(String orderId, String returnReason)`.
2. **Update the sealed hierarchy** so the new subtype is permitted to implement `OrderEvent`.
3. **Recompile all related code**, observing which exhaustive switches report missing cases.
4. **Define the specific policy at each switch site**: auditing, display, notifications, and routing may not handle it the same way.
5. **Add tests** for the new subtype, invalid inputs, and interactions with existing handlers.
6. **Check for unexpected `default` branches** that might be swallowing the new case.
7. **Ensure compatible versions are deployed together**, especially when the domain model and application live in different modules/libraries.

A `default -> null` added just to silence a "non-exhaustive switch" error may make the code compile, but it does not make the system more correct. Treat missing-branch errors as a prompt to clarify business requirements.

### 10.1. When Adding a New Guard

If a rule changes from one threshold to multiple thresholds:

- Identify the unit of `amountVnd` and the boundary values.
- Place more specific branches before general ones.
- Test values just below, equal to, and just above each threshold.
- Avoid guards with side effects; do not execute payments or write state inside `when`.
- Ensure the fallback for the same subtype is not unintentionally removed.

This keeps changes localized and avoids rewriting the entire switch.

## 11. When a Switch Gets Too Long: Handlers, Policies, or Polymorphism

A pattern switch is useful when it acts as a **variant -> behavior map**. However, a very long switch may indicate that a class is taking on too many responsibilities.

**Signals that you should extract:**

- Each `case` contains querying, business validation, persistence, and notification steps.
- The same domain check appears in multiple large switches inconsistently.
- A guard has to call external services, might throw exceptions, or mutates state.
- Testing a single branch requires mocking a slew of unrelated dependencies.

An often effective organization:

```java
// CODE SNIPPET: service/handler defined in the application layer
static void dispatch(OrderEvent event) {
    switch (event) {
        case null -> rejectMissing();
        case OrderCreated created -> onCreated(created);
        case PaymentCaptured paid -> onPaymentCaptured(paid);
        case OrderCancelled cancelled -> onCancelled(cancelled);
    }
}
```

The switch itself is easy to scan; business logic is extracted to handlers.

When a guard condition has complex logic or is used in multiple places, extract it into a **pure policy method** with a clear name, such as `classifyAmount(long amountVnd)`. Extracting it this way creates a single place to test thresholds and avoids duplicating rules across branches.

**Should you replace switches with polymorphism?** Not necessarily. When each subtype owns its own behavior and there are few external operations, polymorphism can make sense. But when the task is rendering DTOs, writing audit logs, or performing operations at the application boundary, switching on a sealed domain is very clear and keeps infrastructure dependencies out of the domain.

Consider what changes more often:

- **Adding subtypes:** sealed + exhaustive switch helps point out the places that need updating.
- **Adding operations over a stable set of subtypes:** adding a switch at the application boundary can be more natural than modifying every subtype.
- **Adding complex classification rules:** extract a policy or state model instead of piling up guards.

## 12. Complete Java 21 Program: Two Switches, One Domain

Save to **`ExtensibleSwitchDemo.java`**. The pattern features used here are standard in Java 21, requiring no preview flags.

```java
public class ExtensibleSwitchDemo {
    sealed interface OrderEvent
            permits OrderCreated, PaymentCaptured, OrderCancelled {}

    record OrderCreated(String orderId, String customerId)
            implements OrderEvent {}

    record PaymentCaptured(String orderId, long amountVnd)
            implements OrderEvent {}

    record OrderCancelled(String orderId, String reason)
            implements OrderEvent {}

    static String describe(OrderEvent event) {
        return switch (event) {
            case null -> "missing event";
            case OrderCreated(var orderId, var customerId) ->
                "created " + orderId + " for " + customerId;
            case PaymentCaptured(var orderId, var amountVnd)
                    when amountVnd >= 1_000_000L ->
                "large payment " + orderId + ": "
                        + amountVnd + " VND";
            case PaymentCaptured(var orderId, var amountVnd) ->
                "payment " + orderId + ": "
                        + amountVnd + " VND";
            case OrderCancelled(var orderId, var reason) ->
                "cancelled " + orderId + ": " + reason;
        };
    }

    static String auditCode(OrderEvent event) {
        return switch (event) {
            case null -> "NO_EVENT";
            case OrderCreated created -> "CREATED";
            case PaymentCaptured paid -> "CAPTURED";
            case OrderCancelled cancelled -> "CANCELLED";
        };
    }

    static void verify(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected [" + expected + "], got [" + actual + "]");
        }
    }

    public static void main(String[] args) {
        OrderEvent[] events = {
            new OrderCreated("ORD-1", "CUS-7"),
            new PaymentCaptured("ORD-1", 1_500_000L),
            new PaymentCaptured("ORD-2", 300_000L),
            new OrderCancelled("ORD-3", "out of stock"),
            null
        };

        for (OrderEvent event : events) {
            System.out.println(
                    describe(event) + " | " + auditCode(event));
        }

        verify("created ORD-1 for CUS-7",
                describe(new OrderCreated("ORD-1", "CUS-7")));
        verify("large payment ORD-1: 1500000 VND",
                describe(new PaymentCaptured("ORD-1", 1_500_000L)));
        verify("payment ORD-2: 300000 VND",
                describe(new PaymentCaptured("ORD-2", 300_000L)));
        verify("large payment ORD-X: 1000000 VND",
                describe(new PaymentCaptured("ORD-X", 1_000_000L)));
        verify("missing event", describe(null));
        verify("CANCELLED",
                auditCode(new OrderCancelled("ORD-3", "out of stock")));

        System.out.println("checks passed");
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 ExtensibleSwitchDemo.java
java ExtensibleSwitchDemo
```

Stdout output:

```text
created ORD-1 for CUS-7 | CREATED
large payment ORD-1: 1500000 VND | CAPTURED
payment ORD-2: 300000 VND | CAPTURED
cancelled ORD-3: out of stock | CANCELLED
missing event | NO_EVENT
checks passed
```

**Why this program demonstrates a good extensible structure:**

- `OrderEvent` clearly defines the set of variants using `sealed`.
- `describe` uses record patterns to extract data and places a guard only on `PaymentCaptured`.
- The guarded branch comes **before** the general `PaymentCaptured` branch.
- `auditCode` uses only type patterns, since record deconstruction is not needed.
- Neither switch uses `default`, allowing the compiler to help detect missing subtypes when the domain expands.
- `case null` explicitly states the policy rather than being confused with a subtype.
- `verify` provides standalone checks without requiring `-ea` or an external test library.

### 12.1. Checking Guard Boundaries

For `amountVnd >= 1_000_000L`, the key values are:

| VND Value | Expected Result |
| ---: | --- |
| 999,999 | regular `payment` |
| 1,000,000 | `large payment` |
| 1,000,001 | `large payment` |

The `verify` call in `main` checks the exact threshold case. In a real application, add the remaining cases to automated unit tests to catch `>` vs. `>=` bugs.

## 13. Organizing Files and Tests as Variants Grow

One possible source code structure for a larger domain:

```text
orders/
  domain/
    OrderEvent.java
    OrderCreated.java
    PaymentCaptured.java
    OrderCancelled.java
  application/
    OrderEventDispatcher.java
    OrderEventFormatter.java
  test/
    OrderEventFormatterTest.java
    OrderEventDispatcherTest.java
```

This is an **optional layout**, not a mandatory rule. Java has specific rules for files containing top-level `public` types; when designing real files, organize them according to those rules. For small examples, nested records in a single class remain completely appropriate.

The separation should reflect:

- **Domain:** variants and data invariants.
- **Application:** routing and business coordination.
- **Presentation:** display results or DTOs.
- **Tests:** verifying behavior for each variant and policy.

Do not let domain records depend directly on email-sending or UI classes just because a switch happens to sit in the wrong architectural layer.

### 13.1. Cases That Need Testing

| Test Group | Coverage |
| --- | --- |
| Each subtype | `OrderCreated`, `PaymentCaptured`, `OrderCancelled` |
| Guard boundaries | Just below, equal to, and just above each threshold |
| Null policy | `null` produces the message or exception required by contract |
| Record components | Order of IDs, amounts, and reasons is not swapped |
| After adding a subtype | Compiler and tests confirm switches/handlers have been updated |
| Integration | Results from real handlers, auditing, persistence, and business side effects |

Compile checks in CI and tests serve different roles: the **compiler** verifies that type/case structure matches, while **tests** verify that results meet business requirements.

## 14. Common Maintenance Mistakes

### 14.1. Adding `default` to Mask Missing Branches

```java
// Compiles, but easily swallows new subtypes:
return switch (event) {
    case OrderCreated created -> "created";
    default -> "other";
};
```

If the domain is closed and every variant needs specific handling, list the concrete subtypes. `default` should be reserved for when there is a genuine fallback policy.

### 14.2. Putting a Broad Case Before a Specialized Case

```java
// INTENTIONALLY WRONG: guarded branch is dominated
case PaymentCaptured(var id, var amount) -> "payment";
case PaymentCaptured(var id, var amount)
        when amount > 1_000_000L -> "large";
```

Fix by moving the guarded case first. Also check the threshold value against business rules.

### 14.3. Using an Overly Broad Selector

If you have an `OrderEvent` and write `switch ((Object) event)`, you lose exhaustiveness information about the permitted subtypes. Do not weaken the static type just for the convenience of writing `default`.

### 14.4. Treating `null` as a Harmless "unknown"

A `null` may be a programming bug or missing external data. Do not automatically return an empty string and let the business flow continue as if a valid event had been processed.

### 14.5. Guards with Side Effects or Overly Long Logic

```java
// Illustrates a structure to avoid when hasPermission has side effects:
case OrderCreated created when hasPermission(created) -> ...
```

If `hasPermission` makes network calls, mutates state, or depends on multiple services, adding guards makes branching flow unpredictable. Perform permission checks with an explicit policy, controlled error handling, and clear operation ordering.

### 14.6. Not Updating Tests When Adding a Subtype

The compiler can catch non-exhaustive switches, but it does not guarantee that message content, fees, amounts, or handlers are processed correctly. After adding a subtype, you must write corresponding business tests.

### 14.7. Assuming Every Switch Must Be Converted to Polymorphism

Converting a clear switch into many abstract handler classes does not automatically improve the design. If the switch mainly classifies data or maps to DTOs, keeping the switch at the application boundary is often easier to understand. Only introduce more classes when there is a clear need for variation and reuse.

## 15. Exercises and Answers

**Exercise 1 — Should there be a `default` or not?**

Given the domain:

```java
sealed interface Alert permits EmailAlert, SmsAlert {}
record EmailAlert(String email) implements Alert {}
record SmsAlert(String phone) implements Alert {}
```

You need an expression that converts each alert type into its own message. Should you write one `case EmailAlert` plus `default`, or two concrete cases?

**Answer:** Given the requirement to handle all subtypes of a closed domain individually, use two concrete cases without `default`. When a new subtype is added, the compiler can flag where handling is needed. Do not forget to define `null` handling explicitly.

**Exercise 2 — Guard ordering:**

```java
case PaymentCaptured(var id, var amount) -> "payment";
case PaymentCaptured(var id, var amount) when amount >= 1_000_000L ->
    "large";
```

**Answer:** Invalid due to dominance. The general branch comes first and shadows the guarded branch. Swap the order and test at the 1,000,000 threshold.

**Exercise 3 — What does a switch expression return if a case has a block?**

```java
case OrderCreated(var id, var customerId) -> {
    String label = id + ":" + customerId;
    yield label;
}
```

**Answer:** `yield label;` supplies the value to the switch expression. The outer `return switch (...) { ... };` is what returns the result from the method.

**Exercise 4 — When to use a type pattern instead of a record pattern?**

**Answer:** When you only need to know the variant, use `case OrderCancelled cancelled ->`; when you directly need `orderId` and `reason`, use `case OrderCancelled(var orderId, var reason) ->`. Both are valid; choose the syntax that communicates intent clearly.

**Exercise 5 — Is a compile check enough?**

**Answer:** No. Exhaustiveness checks that there is a branch for each valid subtype, not that the branch applies the right business rules. You need tests for outputs, thresholds, `null`, and handlers.

**Exercise 6 — What if the input data really is an external `Object`?**

**Answer:** You can use a switch with `case null`, the supported patterns, and `default -> "UNSUPPORTED"`. After validation, convert it to an explicit domain type before deeper processing so you do not lose type checking.

## 16. Code Review Checklist

- [ ] The selector has a static type matching the domain, not needlessly widened to `Object`.
- [ ] Closed subtype sets are modeled with `sealed` where appropriate.
- [ ] Switch expressions handle all variants; no `default` hides new branches when exhaustive checking is desired.
- [ ] The `null` policy is clearly defined.
- [ ] Guarded branches or narrower patterns appear before general branches and are not dominated.
- [ ] Guards are short, free of unpredictable side effects, and tested at boundary values.
- [ ] Record patterns preserve component order and use variable names reflecting the domain.
- [ ] Switch expressions use `yield` properly when a case requires a multi-line block.
- [ ] Branches do not hold too many responsibilities; handlers/policies are extracted when needed.
- [ ] When adding a subtype, related switches, handlers, and tests have been checked.
- [ ] Modules sharing a sealed hierarchy are compiled/deployed compatibly.

## 17. Standard References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch patterns, guards, dominance, null handling, and exhaustiveness in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns finalized in Java 21.
- [Java Language Specification 21, §14.11 — switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): label syntax, switch rules, coverage checking, and switch statement behavior.
- [Java Language Specification 21, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression rules and exhaustiveness.
- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type/record patterns and matching semantics.
- [Java Language Specification 21, §8.1.1.2 — sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): restricting subtypes in a sealed hierarchy.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): practical examples and rules.
