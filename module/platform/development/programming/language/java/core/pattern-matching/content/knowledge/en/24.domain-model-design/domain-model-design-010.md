# Designing Models for Meaningful Patterns in Java (Java 21+)

## 1. The problem to solve

Pattern matching does not make a domain model correct on its own. It helps **recognize data shapes**, **check structure**, and **extract matched components** clearly. If the model still consists only of `String status` and `Object payload`, patterns are often just a nicer syntactic layer laid over ambiguous states.

**Designing models for meaningful patterns** means organizing data so that each pattern branch corresponds to **a real business concept or state**, and valid values carry the exact information that branch needs to process.

For example, in payment processing:

- **Approved**: the payment is approved, with an order ID and a valid receipt.
- **Declined**: the payment is declined, with an order ID and a reason.
- **Pending**: the payment is pending, with an order ID but no approved receipt yet.

If we use these three variants as distinct Java types, `case Approved(...)`, `case Declined(...)`, and `case Pending(...)` are not merely technical conditions: **they express the exact three business branches**.

This article uses **sealed types** (finalized in Java 17, JEP 409), **record patterns** (finalized in Java 21, JEP 440), and **pattern matching for switch** (finalized in Java 21, JEP 441). The examples can be compiled with **JDK 21+**, without needing `--enable-preview`.

## 2. Signs that a model makes patterns meaningless

Consider representing all payment states with a single generic record:

```java
record LegacyPayment(
    String status,
    String orderId,
    Receipt receipt,
    String reason
) {}
```

This snippet is a **model illustration**, assuming `Receipt` is already declared. It allows creating many nonsensical combinations:

- `status = "APPROVED"` but `receipt == null`.
- `status = "PENDING"` but `receipt` and `reason` are already present.
- `status = "DECLINED"` but `reason` is empty.
- `status = "SOMETHING_ELSE"` that the system does not define.

At the processing step, developers are forced to `switch(payment.status())`, manually check nullable fields, cast, or guess the meaning of each string. These conditions are repeated in many places and are not exhaustively checked by the type system.

**This is not a `record` syntax flaw.** It is a sign that the model does not clearly express which data combinations are allowed to exist. Before writing elegant patterns, ask: *which fields does each business variant need, which fields are meaningless for that variant, and what must always be true when creating an object?*

## 3. Step 1: model real variants with a sealed interface

Instead of a single status string shared for everything:

```java
sealed interface PaymentOutcome permits Approved, Declined, Pending {}

record Approved(String orderId, Receipt receipt)
        implements PaymentOutcome {}

record Declined(String orderId, String reason)
        implements PaymentOutcome {}

record Pending(String orderId)
        implements PaymentOutcome {}
```

These are **abbreviated declarations to illustrate structure**; the full runnable version with invariant checks is in section 6.

Design rationale:

- `PaymentOutcome` is the abstract name describing the **payment outcome/state** that a function needs to handle.
- `Approved` carries `Receipt` because a receipt is meaningful and required in the approved state.
- `Declined` carries `reason`; it does not own a meaningless `receipt` field.
- `Pending` only has `orderId`, rather than being “an `Approved` with a null receipt”.
- `sealed ... permits ...` describes the allowed set of subtypes, fitting when this set of variants is **intentionally closed**.

When a `switch expression` traverses `PaymentOutcome`, the compiler knows the allowed subtypes. If a branch is omitted in a `switch` that must be exhaustive, the error can be caught at compile time.

**Limitation:** a sealed hierarchy does not automatically guarantee that the fields inside a record are valid. `new Approved("O-1", null)` can still be created if the constructor does not forbid `null`. Therefore, variant design and **data invariants** are two complementary tasks.

## 4. Step 2: use value objects for meaningful data

A receipt consists of a reference code and an amount. Instead of passing many separate strings/integers across methods, we can use record value objects:

```java
record Money(long cents, String currency) {}
record Receipt(String reference, Money amount) {}
```

In this example:

- `Money.cents` represents the monetary amount in the **smallest unit** (such as cents) to avoid unintended rounding errors when processing values already converted to integer units.
- `Money.currency` represents the currency code. Checking only for three uppercase letters **does not mean** verifying that an ISO 4217 code actually exists.
- `Receipt.reference` is the receipt code, and `Receipt.amount` is a `Money`. These two values belong together according to the business concept.

When records are designed this way, nested patterns become meaningful:

```java
// Inside a switch on PaymentOutcome.
case Approved(
    var orderId,
    Receipt(var reference, Money(var cents, var currency))
) -> ...
```

The pattern reads: *“The approved state of this order, with a receipt having a specific reference code and monetary amount.”* The reader does not need to guess `payload[0]`, `payload[1]`, or cast an `Object`.

**Do not deconstruct every piece of data just to use patterns.** If `Money` has logic for units, conversions, or calculations, keeping `Money money` intact and calling a well-named business method is sometimes better than unpacking components and manipulating integers everywhere.

## 5. Step 3: enforce invariants in constructors

A good model does not just have clear type names: it must prevent creating invalid cases **according to the chosen business domain policy**.

In this payment example, the rules are:

1. Order ID, receipt reference, and decline reason must not be null or contain only whitespace.
2. `Approved` requires a `Receipt`; `Receipt` requires a `Money`.
3. `Money.cents > 0`, because the example models a **positive** payment; refunds, zero amounts, or adjustments may need a different model/rules.
4. `Money.currency` must have the form of **three uppercase ASCII letters**; this is a data-shape check, not a lookup against an actual currency catalog.

Records support a **compact canonical constructor** to validate components upon initialization:

```java
record Money(long cents, String currency) {
    public Money {
        if (cents <= 0) {
            throw new IllegalArgumentException("cents must be positive");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("currency format invalid");
        }
    }
}
```

This is a syntactically standalone declaration, though it can be placed as a nested record inside the program's class. The checks run before the object is successfully instantiated. Java automatically assigns the components after the compact constructor body if no exception is thrown.

For the other records, we can check `receipt != null`, `amount != null`, and that required strings are not blank. From here, objects constructed through valid constructors carry invariants that business code can rely on.

**Note:** `record` guarantees each component is a final field, which does not mean *deep immutability* if a component points to a mutable object. The records in the complete program below contain only primitives, `String`, and controlled record value objects; that is a deliberate choice to reduce the risk of state mutation through references.

## 6. Complete Java example: domain model and patterns expressing the domain together

Create the file **`MeaningfulPatternModelDemo.java`**:

```java
public class MeaningfulPatternModelDemo {
    sealed interface PaymentOutcome permits Approved, Declined, Pending {}

    static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " required");
        }
    }

    record Money(long cents, String currency) {
        public Money {
            if (cents <= 0) {
                throw new IllegalArgumentException("cents must be positive");
            }
            if (currency == null || !currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("currency format invalid");
            }
        }
    }

    record Receipt(String reference, Money amount) {
        public Receipt {
            requireText(reference, "reference");
            if (amount == null) throw new IllegalArgumentException("amount required");
        }
    }

    record Approved(String orderId, Receipt receipt) implements PaymentOutcome {
        public Approved {
            requireText(orderId, "orderId");
            if (receipt == null) throw new IllegalArgumentException("receipt required");
        }
    }

    record Declined(String orderId, String reason) implements PaymentOutcome {
        public Declined {
            requireText(orderId, "orderId");
            requireText(reason, "reason");
        }
    }

    record Pending(String orderId) implements PaymentOutcome {
        public Pending {
            requireText(orderId, "orderId");
        }
    }

    static String describe(PaymentOutcome outcome) {
        return switch (outcome) {
            case Approved(var id, Receipt(var ref, Money(var cents, var currency))) ->
                    "approved:" + id + ":" + ref + ":" + cents + ":" + currency;
            case Declined(var id, var reason) ->
                    "declined:" + id + ":" + reason;
            case Pending(var id) -> "pending:" + id;
            case null -> "missing";
        };
    }

    static void mustReject(String testName, Runnable action) {
        try {
            action.run();
            throw new AssertionError(testName + " was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println(testName + " -> " + expected.getMessage());
        }
    }

    public static void main(String[] args) {
        PaymentOutcome approved = new Approved("O-10",
                new Receipt("R-1", new Money(2500, "USD")));
        PaymentOutcome declined = new Declined("O-11", "insufficient funds");
        PaymentOutcome pending = new Pending("O-12");

        System.out.println(describe(approved));
        System.out.println(describe(declined));
        System.out.println(describe(pending));
        System.out.println(describe(null));

        mustReject("invalid-money", () -> new Money(0, "USD"));
        mustReject("invalid-approved", () -> new Approved("O-13", null));
        mustReject("invalid-reason", () -> new Declined("O-14", ""));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 MeaningfulPatternModelDemo.java
java MeaningfulPatternModelDemo
```

**Exact stdout:**

```text
approved:O-10:R-1:2500:USD
declined:O-11:insufficient funds
pending:O-12
missing
invalid-money -> cents must be positive
invalid-approved -> receipt required
invalid-reason -> reason required
```

The example was executed with JDK 24 using JShell, using language constructs finalized in Java 21. The constructor test section intentionally creates invalid values; if a constructor accepts them, `mustReject` throws an `AssertionError` causing the test to fail, instead of reporting a false success.

### Reading the output by group

| Data | Matched pattern expression | Meaning |
| --- | --- | --- |
| `Approved("O-10", Receipt("R-1", Money(2500, "USD")))` | `Approved(..., Receipt(..., Money(...)))` | Deconstructs data down to the currency unit and returns the approved representation |
| `Declined("O-11", "insufficient funds")` | `Declined(var id, var reason)` | Declined outcome with its own reason |
| `Pending("O-12")` | `Pending(var id)` | Pending state requiring no receipt |
| `null` | `case null` | Handles a missing object, per the demo contract |
| `Money(0, "USD")` | No valid object to match | Constructor rejects because the amount is not positive |
| `Approved("O-13", null)` | No valid `Approved` to match | Constructor rejects due to missing receipt |
| `Declined("O-14", "")` | No valid `Declined` to match | Constructor rejects due to empty reason |

In the success cases, record patterns provide the structure, while string concatenation is the **presentation logic** of the example. Pattern matching does not generate DTOs, format currencies, or implement payment rules on its own.

## 7. Why are these patterns “meaningful”?

### 7.1. Each case reflects a meaningful state

`case Approved(...)` means the order is approved; `case Declined(...)` means it was declined; `case Pending(...)` means it is pending. We do not need to write `if ("APPROVED".equals(status))` and then infer which fields might be null.

**Subtype names** should not be vague technical classifications like `Type1`, `Kind2`. Choose terminology that a domain expert can confirm.

### 7.2. Variant data is placed where it belongs

`Approved` has `Receipt`; `Declined` has `reason`; `Pending` does not carry inapplicable data. Thus, when a pattern matches, the case body does not have to check a series of “may or may not be present” fields just because of a generic model.

Of course, if a field is genuinely **optional in the domain**, represent and check optionality deliberately; do not force every value to be non-null just to make patterns look pretty.

### 7.3. Invariants are enforced where data is created

The compiler can check component **types**, but it cannot prove on its own that an order ID string is non-blank or a monetary amount is positive. Canonical constructors make those rules explicit. Deconstructing structure with patterns is only as safe as **the invariants the model actually enforces**, not promises in documentation.

### 7.4. The compiler helps detect missing branches

Because `PaymentOutcome` is a sealed interface and its records are final subtypes, the `switch expression` in `describe` has cases covering all allowed subtypes, plus `case null` to handle a null selector deliberately.

If you completely remove `case Pending(var id)` without adding another case that covers `Pending`, the compiler rejects the `switch expression` as **non-exhaustive**. This check was tested with JDK 24. When adding a new subtype to `permits` and forgetting to update handling sites, compile errors usually help locate the `switch expression`s that need fixing.

Do not write `default -> "other"` just to avoid handling each subtype: with a closed hierarchy, a `default` branch can hide warnings when a new state appears in the domain. However, if the domain intentionally allows extension by external plugins, a closed sealed type may not fit; in that case, an explicit fallback strategy is needed.

### 7.5. Patterns reveal structure, not replace business rules

`case Approved(var id, Receipt(var ref, Money(var cents, var currency)))` reads data in the **declaration order** of each record. It does not resolve free shipping policies, refunds, exchange rates, or transaction validity. Those rules still belong in service/domain logic, value objects, or clearly named methods.

## 8. Pattern depth: readability matters more than unpacking everything

Nested record patterns are powerful, but they can become hard to read if nested too many levels deep:

```java
case Approved(var id, Receipt(var reference, Money(var cents, var currency))) ->
        "approved:" + id + ":" + cents + currency;
```

In cases where only a method on `Money` is needed, you can keep the meaningful value intact:

```java
// Illustrating a case in a switch on PaymentOutcome.
case Approved(var id, Receipt(var reference, var amount)) ->
        "approved:" + id + ":" + amount;
```

In the second version, `amount` has type `Money` and can be passed to a dedicated formatter. In real business code, keeping the value object intact can avoid spreading `cents`/`currency` details and centralize money-related rules in one place.

**Practical rule:** unpack down to the level needed in the case, not to the deepest level just to show off record patterns.

## 9. Distinguishing valid types from valid values

There are two levels to check:

1. **Type/structural match:** Is it `Approved` or `Declined`? How many components does the record have? Do subpatterns have compatible types? The compiler and pattern matching provide strong support here.
2. **Business validity:** Is `orderId` blank? Is `Money.cents` positive? Is `currency` in the accepted list? This is the job of constructors, validation, and business rules.

An example of a guard on matched data:

```java
// Placed inside a method with a PaymentOutcome outcome variable.
if (outcome instanceof Approved(
        var id, Receipt(var ref, Money(var cents, var currency)))
        && cents >= 10_000) {
    System.out.println("large-approved:" + id);
}
```

`&&` short-circuits: the `cents >= 10_000` condition is evaluated only after the entire record pattern has matched. The `cents` variable is available on the right-hand side and in the true `if` branch thanks to **flow scoping**. The `10_000` threshold is just an illustrative rule for “large amount”, not a universal payment standard.

**`null`:** `case null` in `switch` handles **the `outcome` selector itself being null**. For a nested record pattern `Receipt(...)`, a `receipt == null` will not match. In the model in section 6, `Approved`'s constructor actively rejects a null receipt, so properly constructed objects do not have that situation. However, if you use `var receipt` to extract a nullable component in another model, `var` can still bind null; pattern matching does not turn every component into non-null.

## 10. Mistakes when designing models for patterns

| Mistake | Why it is suboptimal and how to improve |
| --- | --- |
| Having a single `record Event(String type, Object payload)` for all event types | Still requires manual tags, casts, and validation. Consider specialized subtypes or an adapter converting from an external envelope to internal types. |
| Using one large record with 10 nullable fields for 4 states | Allows many meaningless combinations. Split into subtypes by state when states genuinely have different data sets. |
| Adding `sealed` without checking invariants | `new Approved(id, null)` can still be created if the constructor allows it. Add checks and negative tests. |
| Using many `case`s with technical class names | Readers cannot understand the business meaning. Name types, states, and value objects in domain language. |
| Nesting record patterns through too many layers just to avoid accessor calls | Easily becomes hard to read and tightly coupled to record structure. Keep value objects when they have useful behavior. |
| Writing `default` in every sealed `switch` | Can hide cases where the domain adds a new subtype; consider an exhaustive switch without `default`. |
| Assuming `record` is always deeply immutable | Components are final, but may reference mutable objects. Use immutable value objects and defensive copies when needed. |
| Assuming `var x` eliminates null | A `var` pattern on a component can bind null. Use appropriate constructors/validation/guards. |
| Putting all business logic in one very long `switch` | Patterns can select the variant, but substantial logic should live in services or domain methods/polymorphism, depending on responsibility. |
| Using a sealed type for a domain that needs free extension by third parties | A closed subtype set can hinder plugin architectures. Choose an open interface, registry, or polymorphism when extensibility is truly needed. |

## 11. Bringing the model into a real system

A system typically receives JSON, queue messages, or database records before constructing a `PaymentOutcome`. Never assume that an `"APPROVED"` string from the network is already a valid `Approved`.

Recommended workflow:

1. **Read external data** using an appropriate parsing/deserialization mechanism.
2. **Validate source structure**: tags, required fields, data types, formats, and nulls.
3. **Convert to domain types** via constructors/factories, enforcing invariants; return clear parse/validation errors on failure.
4. **Run business logic** on the typed `PaymentOutcome`, using patterns in `switch` or `instanceof` to select behavior.
5. **Convert to output** (API response/DTO/event) with separate mapping and serialization.

If the public API still requires a type tag, keep the tag in the **boundary DTO** and convert to the typed hierarchy internally. There is no need to change the wire format just for nice pattern matching.

**Note on errors:** Throwing exceptions in constructors is an appropriate way to illustrate invariant violations. For untrusted external data, you may prefer parse results with error codes so the system can handle, log, and return clear messages; do not swallow all errors into `null` if you need to distinguish causes.

## 12. Testing checklist for the model and pattern branches

| Test group | Scenario | Expected outcome to verify |
| --- | --- | --- |
| Valid variant | Valid `Approved` + `Receipt` + `Money` | `Approved` branch is selected, components extracted accurately |
| Valid variant | `Declined` with reason | `Declined` branch is selected, no `Receipt` required |
| Valid variant | `Pending` with orderId | `Pending` branch is selected |
| Null selector | `describe(null)` | `case null` branch runs per contract |
| Amount invariant | `Money(0, "USD")` | Constructor rejects because amount is not positive |
| Reference invariant | `Approved(id, null)` | Constructor rejects missing receipt |
| String invariant | `Declined(id, "")` | Constructor rejects empty reason |
| Format boundary | Currency is not three uppercase letters | Constructor rejects per pattern rule |
| Exhaustiveness | Remove `Pending` case in `switch expression` | Compiler reports non-exhaustive switch |
| Model change | Add a new permitted subtype | Exhaustive switches must be updated |
| External data | JSON with valid tag but missing/wrong-type field | Parse/validation error before business logic runs |

**Two different kinds of QA:** Runtime tests prove behavior with data; negative compile tests prove the compiler blocks a construct that does not cover all subtypes. Do not put an intentionally invalid syntax snippet into the runnable example file.

## 13. Exercise: design a model so patterns reflect the domain

Problem: a delivery request can be `Delivered` (with a confirmation code), `Lost` (with a reason), or `InTransit` (with a route ID). Please:

1. Define `sealed interface DeliveryState` with three implementing records, keeping only the components meaningful for each state.
2. Write compact constructors so that the shipment ID and required data are not blank.
3. Write `describe(DeliveryState state)` using a `switch expression` over the three subtypes; decide how to handle `null`.
4. Write a negative test case for a `Delivered` missing its confirmation code, and a check for missing branches when adding a new subtype.

**Model hint** (abbreviated, without validating constructors):

```java
sealed interface DeliveryState permits Delivered, Lost, InTransit {}
record Delivered(String shipmentId, String confirmation)
        implements DeliveryState {}
record Lost(String shipmentId, String reason)
        implements DeliveryState {}
record InTransit(String shipmentId, String routeId)
        implements DeliveryState {}
```

**Handling pattern hint** (placed inside a method with a `DeliveryState state` variable):

```java
String message = switch (state) {
    case Delivered(var id, var confirmation) ->
            "delivered:" + id + ":" + confirmation;
    case Lost(var id, var reason) -> "lost:" + id + ":" + reason;
    case InTransit(var id, var route) -> "transit:" + id + ":" + route;
    case null -> "missing";
};
```

A complete solution also needs constructors that validate required values. Try the case `new Delivered("S-1", null)` to ensure the model does not allow creating “delivered but missing confirmation” under the chosen policy.

## 14. Summary

Patterns are meaningful when **data type structures accurately reflect domain choices**. Sealed hierarchies express allowed variants; record value objects hold meaningful data; constructors protect invariants; type/record patterns select and unpack variants; exhaustive `switch expression`s help catch omitted branches. However, business rules, external data validation, mapping, and extensibility requirements still must be designed separately. **Design the model first, then let patterns express the model — do not design a model merely to showcase pattern syntax.**

Official documentation:

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
