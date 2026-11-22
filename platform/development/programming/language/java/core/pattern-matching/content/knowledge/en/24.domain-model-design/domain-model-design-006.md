# Placing Behavior in the Domain Type or in a Switch?

**Context:** Designing a domain model in Java, especially when data is represented using a `sealed interface` and `record` types, while consumers can use pattern matching for `switch` (Java 21).

## 1. The Design Question

Suppose an application has multiple types of discount policies: a percentage-based discount or a fixed-amount discount. We need two things:
- **Calculate the discount amount and the payable amount** according to business rules.
- **Generate a display label** for reporting, such as `"Percent 10%"` or `"Fixed 175c"`.

There are two ways to organize behavior:
1. **Behavior lives in the domain type:** Each subtype has its own method implementing the same contract. The caller uses **polymorphism**: `policy.discountCents(subtotal)`.
2. **Behavior lives outside the domain type:** A function on the consumer side uses a **pattern switch** to separate the subtypes and perform the corresponding work: `switch (policy) { case Percent(...); case Fixed(...); }`.

Both are valid Java. A good decision depends on **who owns the rule**, **the dependency direction between modules**, and whether the system changes more often along the axis of **data variants** or **operations**. You should neither conclude that `switch` is always a code smell nor put every method on an entity just to avoid `switch`.

**Lesson objectives:** After this lesson, you will be able to distinguish domain behavior from consumer behavior, understand the trade-offs of polymorphism and pattern switches, choose where to place behavior in a domain model with multiple subtypes, properly handle `sealed`, `record`, null, and exhaustive switches, and recognize anti-patterns when refactoring.

**Version:** Examples use **Java 21**. Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have both been standard features since Java 21, requiring no `--enable-preview`.

## 2. Distinguishing Domain Behavior from Consumer Behavior

**Domain behavior** expresses the core rules of a business concept: for example, a policy calculating a discount, an order checking cancellation conditions, or a balance checking withdrawal conditions. It is usually directly tied to **domain invariants**: conditions that must always hold true so the model is never in an invalid state.

Examples of invariants for the discount policy in this lesson:
- Discount rate from **0 to 100** percent.
- Fixed discount amount is **non-negative**.
- Input subtotal in this lesson is **non-negative**.
- Applied discount **does not exceed the subtotal**, and the remaining payable amount is non-negative.

These rules must hold true whether the transaction is created from the web, mobile, or another API. If every controller or UI recalculates them on its own, the risk of logic divergence is very high.

**Consumer behavior** serves a specific use of the domain data and is not necessarily a responsibility of the domain object. For example:
- Displaying labels or translations in the UI.
- Mapping to DTO/JSON for a partner.
- Generating rows in an accounting report.
- Selecting an email template, generating audit information.
- Converting data into an infrastructure format or protocol.

These operations **read domain data**, but that does not mean `DiscountPolicy` should know about HTML, i18n, REST, databases, or email delivery systems.

### A Quick Test

Ask: **“If we replace the UI, database, or external API, must this rule still hold true?”**

- If **yes**, the behavior tends to belong to a domain type or domain service.
- If **no**, it can belong to an application service, mapper, presentation layer, or adapter.
- If a business rule needs to coordinate multiple entities without a natural single owner, a **domain service** may be more appropriate than forcing one entity to carry everything.

This classification is a design guideline, not a rigid rule.

## 3. The DiscountPolicy Model

A simple sealed hierarchy:

```text
DiscountPolicy (sealed interface)
├── Percent(rate)        — record
└── Fixed(amountCents)  — record
```

`DiscountPolicy` describes the discount calculation contract; `Percent` and `Fixed` are two data variants with the same behavior but different formulas.

### Placing the Business Formula in the Subtypes

```java
// Illustrates domain structure; the full runnable program is in section 5.
sealed interface DiscountPolicy permits Percent, Fixed {
    int discountCents(int subtotalCents);

    default int payableCents(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }
        return subtotalCents - discountCents(subtotalCents);
    }
}
```

Both subtypes must implement `discountCents`:

```java
record Percent(int rate) implements DiscountPolicy {
    Percent {
        if (rate < 0 || rate > 100) {
            throw new IllegalArgumentException("rate must be 0..100");
        }
    }

    @Override
    public int discountCents(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }
        return (int) (((long) subtotalCents * rate) / 100);
    }
}

record Fixed(int amountCents) implements DiscountPolicy {
    Fixed {
        if (amountCents < 0) {
            throw new IllegalArgumentException("negative amount");
        }
    }

    @Override
    public int discountCents(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }
        return Math.min(subtotalCents, amountCents);
    }
}
```

**Key design points:**

- **Polymorphism:** `policy.discountCents(subtotal)` invokes the appropriate implementation based on the runtime subtype. The caller does not need `instanceof` or casting.
- **Validation upon creation:** Each record's compact constructor rejects invalid policies, avoiding duplicated validation across consumers. For these records, the components are primitives, so there is no null reference issue.
- **Discount does not exceed subtotal:** The fixed policy uses `Math.min`; the percentage rate is within 0..100 so the discount never exceeds the subtotal.
- **Arithmetic avoiding intermediate overflow:** Cast `subtotalCents` to `long` before multiplying by the percentage. For a non-negative `subtotalCents` within `int` range and a rate of 0..100, the result after dividing by 100 fits in `int`.
- **Rounding:** Integer division with non-negative numbers truncates to the integer number of cents; this is an *illustrative rounding policy*, not automatically suitable for every currency.
- **Method names in domain language:** `discountCents` and `payableCents` describe a business capability, not tied to a specific UI or adapter.

The code uses `int` in cents for ease of learning. Real monetary systems need consistent currency, precision, rounding policies, and may use value objects or `BigDecimal`.

**Note on records:** `record` is well-suited for field-level immutable value types such as policy configurations. You should not default to turning every entity with identity, lifecycle, and mutable state into a record.

## 4. External Display Behavior: Pattern Switch

A reporting system wants to represent each policy with a label. Labels can be **presentation/adapter** behavior rather than discount calculation rules. With Java 21, we can write:

```java
// Illustrative snippet in a class using DiscountPolicy:
static String viewLabel(DiscountPolicy policy) {
    return switch (policy) {
        case Percent(int rate) -> "Percent " + rate + "%";
        case Fixed(int amountCents) -> "Fixed " + amountCents + "c";
        case null -> "No policy";
    };
}
```

This is an **external operation** using **record patterns**. `case Percent(int rate)` matches a `Percent` object and binds the `rate` component in a single step; no cast is needed. The same applies to `Fixed`.

`DiscountPolicy` is `sealed`, with only two record subtypes `Percent` and `Fixed`; both are final types. Therefore, the `switch expression` exhaustively handles every non-null value in the hierarchy. `case null` handles a null selector separately, so no `default` is needed in this example.

**Why not add `viewLabel()` to the domain type?** The label `Percent 10%` might only serve one type of report. Later, the UI may need a Vietnamese translation, financial reports may need the code `PCT`, and a partner API may need a DTO. If every variant had to implement `renderHtml`, `toPartnerJson`, `accountingLabel`, the domain API would be dragged along by external changes. Consumer-specific pattern switches let each adapter own its own representation.

**Do not equate reading data with owning rules:** An external `switch` reads `rate` or `amountCents` to build a label, but it should not rewrite the discount calculation formula in every adapter.

## 5. Complete Java 21 Program: Combining Both Approaches

Create the file **`DomainBehaviorPlacementDemo.java`**:

```java
public class DomainBehaviorPlacementDemo {
    sealed interface DiscountPolicy permits Percent, Fixed {
        int discountCents(int subtotalCents);

        default int payableCents(int subtotalCents) {
            if (subtotalCents < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            return subtotalCents - discountCents(subtotalCents);
        }
    }

    record Percent(int rate) implements DiscountPolicy {
        Percent {
            if (rate < 0 || rate > 100) {
                throw new IllegalArgumentException("rate must be 0..100");
            }
        }

        @Override
        public int discountCents(int subtotalCents) {
            if (subtotalCents < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            return (int) (((long) subtotalCents * rate) / 100);
        }
    }

    record Fixed(int amountCents) implements DiscountPolicy {
        Fixed {
            if (amountCents < 0) {
                throw new IllegalArgumentException("negative amount");
            }
        }

        @Override
        public int discountCents(int subtotalCents) {
            if (subtotalCents < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            return Math.min(subtotalCents, amountCents);
        }
    }

    static String viewLabel(DiscountPolicy policy) {
        return switch (policy) {
            case Percent(int rate) -> "Percent " + rate + "%";
            case Fixed(int amountCents) -> "Fixed " + amountCents + "c";
            case null -> "No policy";
        };
    }

    static void report(DiscountPolicy policy, int subtotalCents) {
        System.out.println(
            viewLabel(policy)
                + ": discount=" + policy.discountCents(subtotalCents)
                + ", payable=" + policy.payableCents(subtotalCents));
    }

    public static void main(String[] args) {
        int subtotal = 1000;
        report(new Percent(10), subtotal);
        report(new Fixed(175), subtotal);
        report(new Fixed(1200), subtotal);
        System.out.println(viewLabel(null));

        try {
            new Percent(101);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid rate");
        }

        try {
            new Fixed(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected negative amount");
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 DomainBehaviorPlacementDemo.java
java DomainBehaviorPlacementDemo
```

Stdout output:

```text
Percent 10%: discount=100, payable=900
Fixed 175c: discount=175, payable=825
Fixed 1200c: discount=1000, payable=0
No policy
Rejected invalid rate
Rejected negative amount
```

### Output Analysis

| Input | Domain rule | Result |
| --- | --- | --- |
| Subtotal 1000 cents, `Percent(10)` | 10% of 1000 = 100 | Payable 900 |
| Subtotal 1000 cents, `Fixed(175)` | 175 cents discount | Payable 825 |
| Subtotal 1000 cents, `Fixed(1200)` | Discount capped at subtotal | Payable 0 |
| `viewLabel(null)` | Display rule allows missing policy | `No policy` |
| `Percent(101)` | Constructor rejects rate greater than 100 | `Rejected invalid rate` |
| `Fixed(-1)` | Constructor rejects negative amount | `Rejected negative amount` |

**Key observations:**
1. `report` calls `policy.discountCents` and `policy.payableCents` without needing to know whether it is `Percent` or `Fixed`.
2. `viewLabel` uses `switch` because its logic is **how to present** the two variants, not the monetary formula.
3. Both the constructors and the calculation methods enforce validity conditions, preventing external classes from using a policy with invalid parameters without checks.
4. `viewLabel(null)` is supported, whereas `report(null, ...)` is not allowed under the current contract: invoking a method on null throws `NullPointerException`. Boundaries receiving data should have an explicit null policy, such as checking `Objects.requireNonNull(policy)`.

For presentation in a standalone runnable file, `viewLabel` is placed next to the model. In a real project structure, it can be moved to a reporting/adapter package; the domain core does not need to depend on label formatting.

## 6. Can the Entire Formula Be Placed in a Switch?

In terms of Java syntax, you can write a function outside the domain type to calculate the amount using a pattern `switch`:

```java
// ILLUSTRATIVE SNIPPET of an alternative design: do not add to the section 5 program
// when discountCents already exists, to avoid maintaining two duplicate formulas.
static int discountViaSwitch(
        DiscountPolicy policy, int subtotalCents) {
    if (subtotalCents < 0) {
        throw new IllegalArgumentException("negative subtotal");
    }

    return switch (policy) {
        case Percent(int rate) ->
            (int) (((long) subtotalCents * rate) / 100);
        case Fixed(int amountCents) ->
            Math.min(subtotalCents, amountCents);
        case null ->
            throw new IllegalArgumentException("Missing policy");
    };
}
```

This snippet is an **alternative design choice**, not something to run in the complete example. It is syntactically valid within the scope where the types are defined.

**The problem is not the `switch` keyword.** The problem occurs when multiple modules independently recalculate the same business rule:

```text
API controller  -> switch policy -> calculate discount independently
Batch processor -> switch policy -> calculate discount independently
Checkout UI     -> switch policy -> calculate discount independently
```

If the rounding method or discount cap changes without updating all three in sync, results can diverge. When the calculation belongs to a domain we control, centralizing it in `DiscountPolicy`/subtypes or a domain service provides much better consistency.

**Situations where an external switch still makes sense:** the data is a DTO from an external SDK that cannot be modified, the operation is used in only one consumer, or the business logic coordinates multiple objects without a natural single owner. In that case, placing the algorithm in a dedicated domain service can still preserve proper business boundaries without injecting methods into DTOs.

## 7. Comparison Table: Domain Methods vs. External Pattern Switch

| Criterion | Domain type + polymorphism | External pattern switch |
| --- | --- | --- |
| Example | `policy.discountCents(subtotal)` | `case Percent(int rate) -> ...` |
| Location of behavior | Attached to the type/subtype contract | In consumer/service/adapter |
| Best suited for | Business rules, invariants, stable shared behavior | Mapping, display, classification, consumer operations |
| Caller dependency | Primarily on interface/contract | Knows concrete subtypes |
| Adding a subtype | New subtype must implement abstract methods | Exhaustive switches may need a new case |
| Adding an operation | Adding a method to the API may impact subtypes | Add a separate function/switch without editing subtypes |
| Compiler support | Reports missing method implementations | Reports missing coverage on sealed/eligible hierarchies |
| Risk | Domain bloated with UI/transport concerns | Domain rules scattered across many consumers |
| Null | Caller needs an object to invoke methods | Can handle via `case null` as needed |
| Testing | Unit test each policy and contract | Test each mapping, fallback, and variant |

These points are **not absolute**: Java interfaces have `default` methods to share behavior; `switch` does not have to be used everywhere; a domain service outside an entity can still be the right place for business behavior. The goal is to reduce coupling and avoid duplicating rules.

## 8. Two Axes of Change: More Subtypes or More Operations?

This is one perspective on the **expression problem**: a design that makes it easy to add **data variants** may be less convenient when adding **new operations**, and vice versa.

### 8.1. Frequently Adding Policy Types, Stable Contract

For example, adding `Tiered`, `Loyalty`, or `CampaignBased`, while every policy still needs to answer `discountCents(subtotal)`.

Polymorphism helps: checkout code calls the same API without adding `if (policy instanceof ...)` chains whenever a subtype is introduced. The new subtype is responsible for implementing its formula.

**Note:** If the hierarchy is `sealed`, you still have to update `permits` and external exhaustive switches (such as report labels). Polymorphism does not guarantee “adding a type without touching anything anywhere”; it **stabilizes callers of the core behavior**.

If you need to support partner plugins extending subtypes arbitrarily, an extensible interface or Strategy pattern may fit better than a sealed hierarchy. When the subtype set is open, an external `switch` cannot rely on a closed list of leaf types to guarantee exhaustiveness.

### 8.2. Stable Subtypes, Many New Operations

Suppose `Percent` and `Fixed` are two fixed types, while consumers continually request:
- Web labels.
- Mobile translations.
- Mapping to accounting DTOs.
- Operations support log formatting.
- Classification codes in reports.

Putting `toMobileLabel`, `toAccountingJson`, `toAuditRow` all onto `DiscountPolicy` can bloat the interface. Each consumer can create an **external operation** over the sealed hierarchy, using a pattern `switch` and getting compiler reminders if a new subtype appears.

**Boundary:** Having many different presentation operations is reasonable; having many implementations of **the same business calculation** is not.

### 8.3. Both Types and Operations Change

In large systems, you can combine them:
- Core interfaces hold the most enduring behaviors.
- Subtypes hold local rules and invariant checks.
- Domain services centralize rules spanning multiple concepts.
- Presentation/integration adapters use pattern switches when they need to read each specific subtype.
- Unit and integration tests verify contracts between modules.

Do not pick an absolute style. Observe **when a requirement changes, how many files and classes must be edited**, and where bugs are most likely to occur.

## 9. Domain Service as a Third Option

The question “domain type or switch?” does not necessarily have only two answers.

A business rule may involve **multiple entities**: account limits, customer privileges, order history, promotion dates. It is not always natural to put the entire rule on `Order` or `DiscountPolicy`.

When there is no clear single object owner, a **domain service** can hold the business algorithm (pure or depending on appropriate abstractions), while an **application service** orchestrates transactions, reads repositories, and invokes adapters.

Example processing flow:

```text
API/Controller
    -> Application service
        -> Repository: fetch Order, Customer, DiscountPolicy
        -> Domain service: check coordination rules
        -> DiscountPolicy.discountCents(): each policy's rule
        -> Repository: persist result
    -> Presentation mapper: switch policy to build DTO
```

The principle is **dependency direction**: the domain should not need to know about HTTP protocols, persistence libraries, HTML formatting, or email providers to execute business rules. A switch inside a domain service is not inherently wrong; however, a switch in a controller deciding all domain invariants on its own is usually a design signal worth revisiting.

## 10. When Should You Use a Switch Inside the Domain?

An external pattern switch can also make sense **right inside the domain** when:

1. The operation is a **one-off conversion/classification** over a closed set of variants that does not need to become a contract for every subtype.
2. The data types are DTOs/value objects from another library that the domain does not own, so methods cannot be added to each class.
3. An algorithm involves multiple variants simultaneously, with no single natural object owning the entire behavior.
4. The domain has a closed set of data types, while **operations** are added more frequently than data types.
5. You want compiler-checked exhaustiveness instead of manual casts/`if` chains.

For example, an independent auditing operation might generate a classification code like this:

```java
// Illustrative snippet of a class using DiscountPolicy:
static String auditCategory(DiscountPolicy policy) {
    return switch (policy) {
        case Percent(var rate) -> "RATE_BASED";
        case Fixed(var amountCents) -> "AMOUNT_BASED";
        case null -> "NONE";
    };
}
```

If the `RATE_BASED` code only serves the audit system, there is no need to force every policy to have an `auditCategory()` method. If it becomes a core regulatory classification that all systems must agree on, consider promoting it to a domain concept or a shared domain service.

## 11. Anti-Patterns When Placing Behavior

### 11.1. Anemic Domain Model: All Rules Live Outside

A notable warning sign is entities/value objects that only contain getters, while every controller and batch job writes:

```java
// Illustrative code of a structure prone to duplication:
if (policy instanceof Percent p) {
    // Calculate percentage discount in consumer A
} else if (policy instanceof Fixed f) {
    // Calculate fixed discount in consumer A
}
// Consumer B/C then copy the same algorithm.
```

If this logic is truly **the same core business rule**, duplication easily causes checkout, batch, and API results to drift. Look for a domain contract like `discountCents` and move the rule back to its proper owner.

**Do not confuse:** A domain model that primarily carries immutable data is **not automatically anemic** if it is intentionally designed that way and business logic lives in domain services with clear responsibilities. The issue lies in scattering and lack of rule ownership, not merely the number of methods on a record.

### 11.2. Fat Domain Model: Stuffing Every Non-Domain Detail Inside

The opposite extreme is an entity having `sendEmail()`, `renderHtml()`, `toPartnerJson()`, and `saveToDatabase()`. Those methods can drag the domain into infrastructure dependencies, making testing hard and UI/SDK changes difficult.

Instead, keep the domain API focused on business meaning. Place mapping, I/O protocols, and formatting in adapters; use pattern switches when you genuinely need to distinguish subtypes.

### 11.3. Giant Switch and Error-Hiding Fallback

If a `switch` has cases hundreds of lines long containing database access, logging, retries, and business rules, extract handler methods and keep the switch purely for dispatching. On a sealed hierarchy, avoid adding an unconditional `default` when an important requirement is **detecting unsupported subtypes** after adding a new type.

### 11.4. Overusing Patterns for Short Syntax

`case Percent(int rate)` may read components nicely, but **pattern matching does not replace behavior on its own**. A domain method call remains clearer and more appropriate when the caller only needs the result of `discountCents`. Do not assume `switch` is faster than dynamic dispatch; evaluating performance requires measuring on real use cases.

## 12. Sealed, Null, Records, and Limitations to Remember

**Sealed is not deep immutability.** `sealed` controls subtypes; `record` creates final fields, but if a record holds a reference to a mutable object, the referenced object can still be mutated. In the example, `Percent` and `Fixed` only have `int` fields, avoiding this issue.

**Switch exhaustiveness.** With `DiscountPolicy` sealed and `Percent`/`Fixed` final, Java 21 can verify that a `switch expression` has a case for every subtype. If you add a new subtype without adding a case, the next compilation will report a non-exhaustive switch. In systems using `non-sealed` or open interfaces, listing a few subtypes does not guarantee full coverage.

**Null selector vs. null method call.** `case null` in `viewLabel` intentionally accepts null. `policy.discountCents` requires an object; calling it on null will fail. The domain API should state clearly whether null input is accepted.

**Record deconstruction only applies to records.** For regular classes, you can use a type pattern like `case SomeClass x` and call methods on that class; you cannot use `SomeClass(...)` deconstruction if it is not a record.

**Domain logic vs. formatting.** The demo program represents money in `cent` using `int`. Real projects should have monetary types and precise rules for rounding, scale, and currency; do not put them in a formatter just because the formatter has a switch.

## 13. Testing and Decision Workflow

### Testing Domain Behavior

You should test:
- `Percent(0)`, `Percent(100)`, subtotal of 0, and large subtotals.
- `Fixed` less than, equal to, or greater than the subtotal.
- `Percent(-1)`, `Percent(101)`, `Fixed(-1)` must be rejected.
- Negative subtotals must be rejected; total payable amount must be non-negative.
- Rounding by currency unit matches the specification.

### Testing External Operations

You should test:
- Correct labels for `Percent` and `Fixed`.
- `null` behaves according to the contract.
- When a new subtype is added, the build/tests require updating the corresponding mapping.
- Formatters do not alter business calculations.

### Review Checklist Before Choosing Where to Place Behavior

1. Is this rule an **invariant or core domain contract**? If yes, favor a domain type/domain service.
2. Does it belong to **formatting, UI, partner API, or infrastructure**? If yes, consider an adapter/consumer.
3. Does the caller need to know the subtype to use the rule? If no, polymorphism keeps callers simple.
4. Is the hierarchy **sealed/closed** and owned by the team? If yes, a pattern switch helps keep external operations exhaustive.
5. Does the system more often **add variants** or **add operations**? Choose the structure that minimizes edits along the more frequently changing axis.
6. Are **multiple consumers duplicating the same formula**? If yes, centralize the domain rule.
7. Does the rule span multiple entities with no single owner? Consider a **domain service**.
8. Would putting the method on the type pull the domain into HTTP, DB, email, or i18n dependencies? If yes, revisit the boundary.
9. Does the pattern switch hide new subtypes behind a `default`? If explicit coverage is required, preserve compile-time checking.
10. Are there unit/integration tests verifying the behavior and the impact of changes?

## 14. Practice Exercises

**Exercise 1 — Add a variant:** Add `record Bonus(int points) implements DiscountPolicy` and update `DiscountPolicy`'s `permits` clause. Specify that `Bonus` discounts by points, capped at the subtotal, and `points` must be non-negative. Explain why `report` still calls `discountCents` correctly without handling the subtype via casting, while `viewLabel` must add a new `Bonus` case to remain exhaustive.

**Exercise 2 — Add an operation:** Create an `accountingCode(DiscountPolicy policy)` function in the integration layer that returns `PCT`, `FIX`, or `NONE`. Use `switch` and explain why there is no need to put accounting codes into each record if it is a partner-specific convention.

**Exercise 3 — Dependency analysis:** A team proposes adding `sendDiscountEmail()` to `Percent` and `Fixed`. List the dependencies that could emerge: email gateway, templates, localization, retries. Propose an application service that uses domain data and an email adapter, which can select a template using a pattern switch outside the domain.

**Exercise 4 — Domain service:** A promotional program needs to evaluate `DiscountPolicy`, order history, and customer tier. Distinguish the domain service that calculates eligibility from the application service that fetches data from repositories, opens a transaction, and calls the domain service. State why the entire use case should not be forced into a method on `Percent` or `Fixed`.

## 15. Conclusion

**Place behavior in the domain type** when it is a core capability of the object, protects invariants, or forms a long-term shared contract across multiple subtypes. **Place behavior in the consumer using a pattern `switch`** when the operation is primarily presentation, mapping, or data classification for an external need over a known set of types. **Use a domain service** when business logic coordinates multiple concepts and does not naturally belong to a single type.

Do not choose based on the shortest syntax. Choose based on **business rule ownership, dependency direction, axis of change, and testability**. Java 21 supports both traditional polymorphism and safe pattern matching; combining them in the right places is usually better than applying either extreme.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
