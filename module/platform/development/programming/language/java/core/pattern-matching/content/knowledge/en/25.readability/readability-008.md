# Commenting When Patterns Rely on Invariants (Java 21+)

## 1. The Readability Problem: A Matching Pattern Does Not Guarantee Valid Data

An **invariant** is a condition that must always hold true for an object in states considered valid by the domain. For example: "A sent order must have a non-empty tracking ID", "A shipping address must have a city name", or "The quantity in an order line must be positive".

**Pattern matching** answers a different question: "Does the object have a type and structure matching this pattern, and what values can be extracted from it?". The two concepts complement each other, but **do not replace each other**:

- A **type pattern** checks whether an object has a matching type while declaring a pattern variable, such as `value instanceof String text`.
- A **record pattern** (Java 21+) checks and deconstructs a record, such as `shipment instanceof Shipment(Address(var city, var street), var status, var id)`.
- A **`when` guard or `&&` condition** adds a rule checked at the point of use.
- **Invariants** are enforced by constructors, factories, APIs, or type states; the compiler **does not automatically infer** all business rules merely from a record pattern matching.

For example, when seeing code like:

~~~java
case Shipment(Address(var city, var street), var status, var id)
        when status == Status.SENT ->
        "sent:" + city + ":" + id.toUpperCase(java.util.Locale.ROOT);
~~~

a reasonable reader will ask: **Why can `id.toUpperCase(...)` be called without checking `id != null`?** The right answer must lie in an enforced and verifiable invariant, not in the assumption "because the record pattern matched".

The most useful comment here explains **the hidden condition the code relies on, where that condition is enforced, and why the code is allowed to omit a guard**. A comment that merely says "handle sent order" does not explain the point of risk.

## 2. Domain Scenario: Shipments and Tracking IDs

Build a small model consisting of:

~~~java
enum Status { DRAFT, READY, SENT }

record Address(String city, String street) {}

record Shipment(Address destination, Status status, String trackingId) {}
~~~

In this example, we establish four rules:

1. `Address.city` and `Address.street` must be non-`null` and not consist solely of whitespace.
2. `Shipment.destination` must be non-`null`.
3. `Shipment.status` must be non-`null`.
4. If `Shipment.status == Status.SENT`, then `trackingId` **must be non-`null` and non-blank**. For the remaining statuses, `trackingId` may be `null`; if a value is present, it must not be blank.

This is the **example's business contract**, not a default property of Java records. The initial record declarations above **do not enforce** these rules; values such as `new Shipment(null, Status.SENT, null)` can still be created if validation is not added.

A pattern:

~~~java
input instanceof Shipment(Address(var city, var street),
                          var status, var id)
~~~

only verifies the record type and shape to deconstruct. The pattern does not itself verify that `city` is non-blank or that `status == SENT` requires `id != null`. Therefore, for processing code to rely on invariants, you must first **enforce the invariants in the model**.

## 3. Enforcing Invariants in the Constructor

With records, a **compact constructor** is the natural place to validate inputs before the components are initialized.

~~~java
record Address(String city, String street) {
    Address {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city");
        }
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("street");
        }
    }
}

record Shipment(Address destination, Status status, String trackingId) {
    Shipment {
        if (destination == null) {
            throw new IllegalArgumentException("destination");
        }
        if (status == null) {
            throw new IllegalArgumentException("status");
        }
        if (trackingId != null && trackingId.isBlank()) {
            throw new IllegalArgumentException("trackingId blank");
        }
        if (status == Status.SENT && trackingId == null) {
            throw new IllegalArgumentException("SENT requires trackingId");
        }
    }
}
~~~

These are **illustrative declarations** within the same scope as `enum Status`. The complete standalone program is in section 9.

Compact constructors validate parameters before Java assigns them to the record's components. As a result, normal constructor calls must obey the domain rules:

| Data | Result | Why? |
| --- | --- | --- |
| `new Address("Ha Noi", "Pho Hue")` | Valid | Both strings are non-null and non-blank |
| `new Address(null, "Pho Hue")` | Throws `IllegalArgumentException` | Missing city |
| `new Shipment(address, DRAFT, null)` | Valid | Unsent shipment does not require an ID |
| `new Shipment(address, READY, null)` | Valid | READY status in this example does not require an ID yet |
| `new Shipment(address, SENT, "tk-7")` | Valid | Sent and ID is non-blank |
| `new Shipment(address, SENT, null)` | Throws `IllegalArgumentException` | Violates constraint between status and trackingId |
| `new Shipment(address, SENT, "  ")` | Throws `IllegalArgumentException` | Blank tracking ID |
| `new Shipment(null, DRAFT, null)` | Throws `IllegalArgumentException` | Missing address |

**Two different levels of guarantees:** the compiler knows `trackingId` has type `String`, but does not know that it is non-null when `status == SENT`. The latter condition is a **runtime invariant** enforced by the constructor. Because record components are `final`, normal Java code cannot directly mutate components after creation; however, records are only *shallowly* immutable, so if a component is a mutable object, additional design is needed to preserve invariants throughout its lifecycle.

## 4. Good Comments: State "Why It Is Safe" and "Where It Is Enforced"

Once the constructors protect the invariants, we can write:

~~~java
static String describe(Object input) {
    return switch (input) {
        // Invariant: Shipment(status == SENT) has a non-null,
        // non-blank trackingId. Checked in the Shipment constructor.
        // The Address constructor also guarantees city is non-null and non-blank.
        case Shipment(Address(var city, var street), var status, var id)
                when status == Status.SENT ->
                "sent:" + city + ":"
                        + id.toUpperCase(java.util.Locale.ROOT);

        case Shipment(Address(var city, var street), var status, var id) ->
                "pending:" + city + ":" + status;

        case null -> "null";
        default -> "unsupported";
    };
}
~~~

This is an illustrative method using `Status`, `Address`, and `Shipment` as defined and validated above. The program in section 9 contains the same method.

Breaking down the first branch:

- `Shipment(Address(...), ...)` checks the outer record type and deconstructs the nested `Address` record.
- `var status`, `var id` declare variables whose static types are inferred from the components, `Status` and `String` respectively.
- `when status == Status.SENT` is the condition **actually checked** when selecting the branch.
- That `id != null` and `!id.isBlank()` **is not directly checked by this guard**; it relies on the invariant of the `Shipment` constructor.
- That `city` is non-null and non-blank relies on the validation of the `Address` constructor.

This is the difference between a **compiler guarantee** and a **domain guarantee**. Readers should not be misled into thinking that the record pattern or `when` guard itself creates all of those guarantees.

### Which Comments Are Actually Valuable?

**Weak comment:**

~~~java
// Get shipment info, call toUpperCase, then return the string.
case Shipment(Address(var city, var street), var status, var id)
        when status == Status.SENT ->
        id.toUpperCase(java.util.Locale.ROOT);
~~~

It repeats what the code already shows, but does not explain why the call on `id` is safe.

**Useful comment:**

~~~java
// Shipment constructor guarantees: status == SENT => trackingId != null.
// If you change the condition in the constructor, you must recheck this branch.
case Shipment(Address(var city, var street), var status, var id)
        when status == Status.SENT ->
        id.toUpperCase(java.util.Locale.ROOT);
~~~

The second comment states the **dependency between where the invariant is defined and where it is used**. You can document the invariant as Javadoc on the model so readers find the contract right at the declaration, and then use a brief comment on the branch containing the error-prone operation.

## 5. When Should You Keep a Guard Instead of Only Commenting?

Not every invariant justifies omitting a local check.

### Case A: Tightly Controlled Invariant and Internal Code

If all `Shipment` instances are created through a validating constructor, calling `id.toUpperCase(...)` in the `status == SENT` branch is justified. A brief comment pointing to the constructor and invariant tests is usually enough to explain why no inline null check is needed.

### Case B: Unvalidated Data at System Boundaries

For example, when processing JSON, queue messages, or legacy data: before treating it as a valid `Shipment`, the conversion code must validate/normalize the data according to the contract. You should not write a comment saying "trackingId is always present" on a raw data structure if nothing enforces it.

~~~java
// Raw/unvalidated data: validate before using.
static String safeRawLabel(String id, Status status) {
    if (status == Status.SENT && (id == null || id.isBlank())) {
        return "invalid sent shipment";
    }
    return status == Status.SENT
            ? id.toUpperCase(java.util.Locale.ROOT)
            : "not sent";
}
~~~

This is an **illustrative method**; if `status` can be null, the current function treats null as "not sent". In a real application, you may need to return a specific error for a null status depending on the API contract.

Principle: **validate once at the trust boundary**, then work with valid domain objects. Do not create unvalidated domain objects, rely on comments, and hope every call site remembers to check.

### Case C: Multi-Condition or Evolving Invariants

If the rule is "tracking ID is required when status is SENT **and** shipping type is DELIVERY", a short comment saying "SENT always has an ID" becomes **wrong**. The comment must express the full premise, or the code should have a named method such as `requiresTrackingId()` to centralize the rule. When the rule changes, update the validation, comment, and tests together.

A comment is not an enforcement mechanism. If the invariant is lost due to a model change while the comment remains, that comment becomes a **source of misinformation**.

## 6. Subtlety: A Component Pattern Does Not Prove Non-`null`

This is why special care is needed when commenting based on invariants.

~~~java
record RawShipment(String trackingId, Status status) {}

Object raw = new RawShipment(null, Status.SENT);

if (raw instanceof RawShipment(String id, var state)) {
    System.out.println(id == null); // true on Java 21
}
~~~

Even though `String id` is a type pattern, in a **record component** position whose static type is already `String`, it can be an **unconditional pattern** and match even a `null` component. This differs from a direct `someObject instanceof String text` expression, where an outermost `null` value causes `instanceof` to return `false`.

Therefore, even when code uses `RawShipment(String id, ...)`, **do not automatically conclude** that `id.toUpperCase()` is always safe.

Comparison:

| Form | Does it imply `id != null`? | Why? |
| --- | --- | --- |
| `Object obj = null; obj instanceof String id` | No; the match fails | Top-level `instanceof` does not match null |
| `RawShipment(String id, ...)` with a `String` component | No | An unconditional component pattern can receive null |
| `RawShipment(var id, ...)` | No | `var` only infers the component's static type |
| `Shipment(..., var id) when status == SENT` | Yes, by **enforced domain contract**, not by the pattern | The `Shipment` constructor rejects SENT status without an ID |
| `id != null && !id.isBlank()` | Yes, on the true branch | The guard actually checks the value |

During code review, if you see a method call on a record component variable without a null check, look for the **source of the invariant**. If you cannot find it, add validation or a guard, not just a comment saying "definitely not null".

## 7. What Should a Contract Comment Include?

You do not need to write an essay next to every pattern. For invariant-based logic, comment only when the reader **cannot infer the safety guarantee from the few lines in front of them**.

A short comment should usually answer three points:

1. **Condition:** What is the exact invariant? E.g., `status == SENT => trackingId != null && !trackingId.isBlank()`.
2. **Source of enforcement:** Where is it enforced? E.g., the `Shipment` compact constructor; or a trusted factory or validation layer with tests.
3. **Dependent consequence:** Which pattern branch relies on it, and what change could make the code unsafe?

Example placed on the model:

~~~java
/**
 * Domain invariant: destination != null, status != null;
 * status == SENT => trackingId != null && !trackingId.isBlank().
 * Enforced in the compact constructor.
 */
record Shipment(Address destination, Status status, String trackingId) {
    // Constructor validation in section 3.
}
~~~

This Javadoc snippet is a **documentation illustration**; it has no actual validation body and **must not be treated as a standalone class that enforces invariants**. The complete version with the constructor and tests is in section 9.

At the call site, avoid repeating the entire Javadoc if the contract is already clear. Comment only at the notable point of risk:

~~~java
// Shipment contract: SENT always has trackingId; see compact constructor.
case Shipment(var address, var status, var id)
        when status == Status.SENT -> id.toUpperCase(java.util.Locale.ROOT);
~~~

**Comments should not restate syntax** such as "pattern extracts 3 fields" when that is already obvious. Prioritize explaining **why a check is omitted**, **cross-field constraints**, or **assumptions not visible at the reading site**.

## 8. When Invariants Are Complex: Consider Moving Them Into Types

If the invariant "SENT status must have a tracking ID" appears in many places, repeatedly checking `status` and relying on `trackingId` may be a sign that the model is suboptimal. You can model different states with subtypes:

~~~java
sealed interface ShipmentState
        permits DraftState, ReadyState, SentState {}

record DraftState() implements ShipmentState {}
record ReadyState() implements ShipmentState {}
record SentState(String trackingId) implements ShipmentState {
    SentState {
        if (trackingId == null || trackingId.isBlank()) {
            throw new IllegalArgumentException("trackingId");
        }
    }
}
~~~

This is an **illustrative alternative model**: it puts the `trackingId` payload exclusively into the `SentState`. As a result, the rule "only the sent state has a required ID" is expressed closer to the **type structure**, rather than relying entirely on the relationship between an enum and a nullable field of a large record.

However, subtypes do not automatically enforce all content invariants (such as a non-blank ID); constructors still must validate. A sealed type is a good fit when states have distinctly different payloads or behaviors, while an enum plus validation can be simpler if the model is small and stable. **Do not change the design just to remove a comment**; change it when doing so makes the domain clearer and invalid states harder to construct.

## 9. Complete Java 21 Program with 14 Test Cases

Create the file **`InvariantPatternDemo.java`**:

~~~java
public class InvariantPatternDemo {
    enum Status { DRAFT, READY, SENT }

    record Address(String city, String street) {
        Address {
            if (city == null || city.isBlank()) {
                throw new IllegalArgumentException("city");
            }
            if (street == null || street.isBlank()) {
                throw new IllegalArgumentException("street");
            }
        }
    }

    record Shipment(Address destination, Status status, String trackingId) {
        Shipment {
            if (destination == null) {
                throw new IllegalArgumentException("destination");
            }
            if (status == null) {
                throw new IllegalArgumentException("status");
            }
            if (trackingId != null && trackingId.isBlank()) {
                throw new IllegalArgumentException("trackingId blank");
            }
            if (status == Status.SENT && trackingId == null) {
                throw new IllegalArgumentException(
                        "SENT requires trackingId");
            }
        }
    }

    // Does not enforce invariants: intentionally used to demonstrate the risk.
    record RawShipment(String trackingId, Status status) {}

    static String describe(Object input) {
        return switch (input) {
            // Shipment contract: SENT => trackingId is non-null, non-blank.
            // Address guarantees city is non-null, non-blank.
            // Both are checked in their respective compact constructors.
            case Shipment(Address(var city, var street), var status, var id)
                    when status == Status.SENT ->
                    "sent:" + city + ":"
                            + id.toUpperCase(java.util.Locale.ROOT);

            case Shipment(Address(var city, var street), var status, var id) ->
                    "pending:" + city + ":" + status;

            case null -> "null";
            default -> "unsupported";
        };
    }

    private static int passed = 0;

    static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name);
        }
        ++passed;
        System.out.println("PASS " + name);
    }

    static void expectInvalid(String name, Runnable factory) {
        try {
            factory.run();
            throw new AssertionError("Expected invalid: " + name);
        } catch (IllegalArgumentException expected) {
            check(name, true);
        }
    }

    public static void main(String[] args) {
        Address address = new Address("Ha Noi", "Pho Hue");

        check("sent", describe(
                new Shipment(address, Status.SENT, "tk-7"))
                .equals("sent:Ha Noi:TK-7"));

        check("ready", describe(
                new Shipment(address, Status.READY, null))
                .equals("pending:Ha Noi:READY"));

        check("draft", describe(
                new Shipment(address, Status.DRAFT, null))
                .equals("pending:Ha Noi:DRAFT"));

        check("null-input", describe(null).equals("null"));
        check("other-input", describe("other").equals("unsupported"));

        expectInvalid("null-city",
                () -> new Address(null, "Pho Hue"));
        expectInvalid("blank-city",
                () -> new Address(" ", "Pho Hue"));
        expectInvalid("blank-street",
                () -> new Address("Ha Noi", " "));
        expectInvalid("null-address",
                () -> new Shipment(null, Status.DRAFT, null));
        expectInvalid("null-status",
                () -> new Shipment(address, null, null));
        expectInvalid("sent-without-id",
                () -> new Shipment(address, Status.SENT, null));
        expectInvalid("blank-id",
                () -> new Shipment(address, Status.SENT, " "));

        Object raw = new RawShipment(null, Status.SENT);
        check("raw-null-component",
                raw instanceof RawShipment(String id, var status)
                        && id == null && status == Status.SENT);

        check("record-value-equality",
                new Address("Ha Noi", "Pho Hue").equals(address));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Compile/run with **JDK 21 or later**:

~~~bash
javac --release 21 InvariantPatternDemo.java
java InvariantPatternDemo
~~~

Output:

~~~text
PASS sent
PASS ready
PASS draft
PASS null-input
PASS other-input
PASS null-city
PASS blank-city
PASS blank-street
PASS null-address
PASS null-status
PASS sent-without-id
PASS blank-id
PASS raw-null-component
PASS record-value-equality
ALL PASSED: 14
~~~

### Explanation of Key Results

- **`sent`:** `when status == SENT` selects the branch, and `id.toUpperCase(...)` is safe because the constructor rejects null/blank tracking IDs in the SENT state.
- **`ready`, `draft`:** `trackingId == null` is valid for those two states. The `pending` branch does not dereference `id`.
- **`null-input`, `other-input`:** the pattern takes an `Object` input, handling a null selector and other types explicitly.
- **Seven `expectInvalid` cases:** prove that key invariants are enforced at object creation time, not merely described in comments.
- **`raw-null-component`:** `RawShipment` has no validation; even when using the component pattern `String id`, `id` can still be null. This is the counterexample explaining why patterns **do not replace** invariants.
- **`record-value-equality`:** two `Address` value objects containing the same values are equal according to the `equals` method provided automatically by the record.

The `check` method throws an `AssertionError` if a result is wrong; the program only prints `ALL PASSED: 14` when every check succeeds. The `expectInvalid` method also requires the constructor to actually reject invalid data. The intentionally shortened/explanatory snippets in earlier sections are not standalone programs and do not need to be copied into this file.

## 10. Testing So Comments Do Not Become Stale

An invariant has practical value when protected by code and **regression tests**. You should have at least:

| Test Group | Example | Expectation |
| --- | --- | --- |
| Conditionally valid | `SENT` with trackingId `"tk-7"` | Object created; `sent` branch uses ID safely |
| Valid without field | `DRAFT` with trackingId `null` | Object created; no method called on ID |
| Cross-field relationship violation | `SENT` with trackingId `null` | Constructor rejects |
| Field content violation | `SENT` with whitespace-only trackingId | Constructor rejects |
| Nested component violation | Address with null/blank city | `Address` constructor rejects |
| Top-level null value | `describe(null)` | Selects `case null` branch |
| Raw record without invariants | `RawShipment(null, SENT)` | Component pattern may still match; must not dereference null |
| Variable/guard scope | `when status == SENT` | Only the branch needing the invariant calls `id.toUpperCase(...)` |

In particular, when modifying a constructor, search for places with comments like "per invariant X" and recheck how they use variables from record patterns. Running only "happy path" cases is not enough; negative invariant tests demonstrate that the source of the guarantee still exists.

If using JUnit in a project, you can convert `expectInvalid` to `assertThrows(IllegalArgumentException.class, ...)`, though the example in this article intentionally uses plain JDK so it can run immediately.

## 11. Common Mistakes When Commenting Patterns

**Mistake 1 — commenting claims that the code does not enforce.** Writing "trackingId cannot be null" when the record has no validation misleads readers into thinking a guarantee exists. Add the constructor/factory first, then document where the rule is enforced.

**Mistake 2 — commenting only obvious operations.** "Use switch to branch" provides no information beyond what the syntax already shows. Explain important assumptions or why a guard is omitted instead.

**Mistake 3 — treating record patterns as business validators.** Patterns extract values by structure; they do not automatically check string length, positive amounts, or relationships between status and trackingId.

**Mistake 4 — thinking a `String` component pattern always excludes null.** An unconditional component pattern can receive null, as in the `RawShipment(String id, ...)` case on Java 21. Verify in practice or rely on an enforced invariant, rather than inferring from the type name.

**Mistake 5 — an invariant holds for one data source but is assumed for all sources.** When mapping data from DTOs, databases, or messages into the domain model, identify the validation point before letting pattern logic rely on the invariant.

**Mistake 6 — not updating comments when conditions change.** When changing `SENT` to `SENT || READY`, the comment, constructor, `when` branch, and tests must be reviewed together. A wrong comment is more dangerous than no comment.

**Mistake 7 — ignoring mutable components.** Records are shallowly immutable: if a field points to a mutable collection/object, content invariants can be broken after the constructor runs. Use defensive copies, immutable value objects, or appropriate validation.

**Mistake 8 — replacing every guard with a comment to make "cleaner code".** At untrusted data boundaries, guards or validation must still run. Comments do not stop `NullPointerException` or invalid data.

**Mistake 9 — repeating the same comment across every branch.** Put the contract on the model and add only a brief reminder at risky sites that need explanation. If the same rule appears in too many places, consider introducing a clearly named helper or improving the domain structure.

## 12. Readability Review Checklist

Before accepting a pattern that relies on invariants, ask yourself:

1. **Which conditions are guaranteed by the compiler?** Correct types, structure, pattern variable scope, `switch` exhaustiveness?
2. **Which conditions are guaranteed only by the domain?** Non-blank strings, positive numbers, cross-field relationships, state ordering?
3. **Where is the invariant enforced?** Constructor, factory, or boundary validation? Are there negative tests?
4. **Does the comment accurately state the premise and source of enforcement?** Is there a quick way to trace to the validation site?
5. **If the invariant were removed, how would the pattern usage break?** `NullPointerException`, corrupted data, wrong branch, missing information?
6. **Can the invariant be better expressed with types?** E.g., subtypes with required payloads instead of an enum plus a nullable field.
7. **Has `null` been considered for both the selector and record components?** The two positions do not always have the same matching semantics.
8. **Does it depend on mutable data or an unvalidated source?** If so, another validation point is needed.
9. **When changing the invariant, are related tests and comments updated?**

### Exercises

- Modify `Shipment` so that `Status.READY` also requires a trackingId. Update the validation, tests, and comments, then check which pattern branches rely on the new rule.
- Replace `Address` with a record without validation. Predict how the program will behave when `city == null` and identify where protection is needed if the code wants to call `city.toUpperCase()`.
- Add `Status.CANCELLED`, requiring that this status **must not** have a trackingId. Express the constraint in the constructor and test both directions: null is valid, non-null ID is invalid.
- Compare the `Shipment(status, trackingId)` model with `sealed ShipmentState`/`SentState(trackingId)`: which model better reduces hidden assumptions in processing code?

**Key takeaway:** When a pattern relies on an invariant, a good comment does not re-explain pattern syntax; it clearly states **the implicit guarantee**, **the source enforcing that guarantee**, and **the code path depending on it**. The compiler checks types and pattern variable scope; constructors/validation protect domain validity. The most readable and safest approach clarifies the boundary between these two kinds of guarantees while keeping tests so comments always reflect actual behavior.