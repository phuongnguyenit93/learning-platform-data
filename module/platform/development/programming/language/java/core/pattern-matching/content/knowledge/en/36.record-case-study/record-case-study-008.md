# Testing Data with Missing Components in Java Records — Practical Case Study

## 1. Context and Objectives

Suppose an invoice-processing system receives payloads from an API or a message queue. The domain model uses a `record`:

```java
record Invoice(String id, long cents, String currency) {}
```

The business contract requires `id` and `currency` to be non-blank, and the amount `cents` to be greater than 0. However, an external payload might be missing the `id` key, have `"currency": null`, use `"cents": "500"` instead of a number, or contain invalid data inside a nested record.

**Testing data with missing components** does not mean "calling a record constructor while omitting an argument." A record has a fixed component list at the source level. The real-world scenarios that need testing are **external data missing fields** or **an already-constructed record having components with invalid values**, often due to mapping, deserialization, legacy code, or overly permissive constructors/factories.

By the end of this article, you will be able to:

1. Distinguish between **missing input fields**, **present fields with `null`**, **wrong types**, **invalid values**, and **nested components that are `null`**.
2. Understand how record constructors, accessors, and record patterns behave when components are incomplete.
3. Write tests that classify each scenario in Java 21 with deterministic stdout.
4. Place validation in the right layer: data boundaries, canonical constructors/factories, and pattern matching logic.
5. Avoid assuming that a `record` or an exhaustive `switch` automatically guarantees valid data for every component.

The examples use **Java 21 final** features for record patterns (JEP 440) and pattern matching for `switch` (JEP 441). Record classes have been final since Java 16 (JEP 395).

## 2. "Missing Component" Has at Least Five Different Meanings

| Scenario | Example | Where can it happen? | How to check |
| --- | --- | --- | --- |
| Missing constructor argument in Java code | `new Invoice("I-1", 500L)` | Java source | Compiler rejects it due to wrong number of parameters |
| Missing key in payload | No `"currency"` key | JSON/Map/request | `containsKey`, schema, or validation |
| Key present with `null` value | `"currency": null` | Payload or reference record | Null check / constructor |
| Wrong value type | `"cents": "500"` | Parser, mapping, API | Type pattern or rule-based conversion |
| Valid type but invalid business value | `cents = 0`, `id = " "` | Domain object | Invariant in constructor/factory |
| Nested record missing object | `customer.address == null` | Legacy domain data / DTO | Test nested patterns and fallback |

**Principle:** A Java record defines a **static shape** (names, types, and number of components). It does not automatically verify the completeness of data received through protocols outside Java, nor does it forbid `null` in reference-type components by default.

For example:

```java
record Pair(String left, String right) {}

// The two lines below illustrate two different cases:
new Pair("A", null); // VALID if the record has no validation.
new Pair("A");       // COMPILE ERROR: missing the second argument.
```

The statement `new Pair("A")` is a **negative compile example** and must not be placed in production source files. For a `Pair` record that defines no additional constructors, the canonical constructor has two parameters corresponding to the two components.

Similarly, the pattern:

```java
// INVALID in Java 21: exactly two component patterns are required.
if (value instanceof Pair(var left)) {
    System.out.println(left);
}
```

is rejected by the compiler when `Pair` has two components. Record patterns do not have syntax to "omit trailing components because they are unused." If you want to ignore a component in logic while still writing a pattern, use `Pair(var left, var right)` in Java 21 and only use `left`, or use `Pair pair` and call `pair.left()`.

## 3. Case Study A: Nested Records with Missing Component Values

Consider an order model:

```java
record Address(String city) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer) {}
```

In a permissive version, the records **have no validation**. Java accepts:

```java
new Order("O-5", null);
new Order("O-4", new Customer("An", null));
new Order("O-2", new Customer("An", new Address(null)));
```

Each call still provides **all constructor arguments**, only with a reference component receiving `null`.

This is a common situation when domain models are constructed directly from unvalidated or legacy data. Consumers can use nested record patterns, but they need to know **which patterns match and which do not**.

## 4. Complete Example: Testing Nested Record Patterns and Null

Save the following program to `MissingComponentDemo.java`:

```java
public class MissingComponentDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer) {}

    static String route(Order order) {
        return switch (order) {
            case Order(
                    var id,
                    Customer(var name, Address(String city)))
                    when id != null && name != null && city != null ->
                    "complete:" + id + ":" + name + ":" + city;

            case Order(
                    var id,
                    Customer(var name, Address(var city))) ->
                    "incomplete-city-or-fields:" + id;

            case Order(var id, Customer(var name, var address)) ->
                    "missing-address:" + id;

            case Order(var id, var customer) ->
                    "missing-customer:" + id;

            case null ->
                    "null-order";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(
                new Order("O-1", new Customer(
                        "An", new Address("Hue")))));

        System.out.println(route(
                new Order("O-2", new Customer(
                        "An", new Address(null)))));

        System.out.println(route(
                new Order("O-3", new Customer(
                        null, new Address("Hanoi")))));

        System.out.println(route(
                new Order("O-4", new Customer(
                        "An", null))));

        System.out.println(route(new Order("O-5", null)));
        System.out.println(route(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 MissingComponentDemo.java
java MissingComponentDemo
```

**Expected stdout:**

```text
complete:O-1:An:Hue
incomplete-city-or-fields:O-2
incomplete-city-or-fields:O-3
missing-address:O-4
missing-customer:O-5
null-order
```

### Step-by-Step Explanation

- `O-1`: `Order`, `Customer`, and `Address` are present and `id`, `name`, and `city` are non-null, so the first branch matches.
- `O-2`: `Address` exists, but `city == null`. The first guarded branch fails; the second branch handles this record.
- `O-3`: Customer name is `null`; even though `city` is valid, the first guard fails, so the second branch handles it.
- `O-4`: `Customer` exists, but `address == null`; the nested record pattern `Address(...)` does not match that component. The `Customer(var name, var address)` branch matches.
- `O-5`: `customer == null`; the `Customer(...)` pattern does not match, so the `Order(var id, var customer)` branch matches.
- `null`: The selector itself is null, handled separately by `case null`.

The returned strings illustrate **classification**, not a mandatory domain policy. In production, you can choose to throw an exception, reject the request, or log an observability event depending on the contract.

## 5. An Easy-to-Misunderstand Java 21 Detail: Null-Matching in Component Type Patterns

Do not state a blanket rule that "every `String s` pattern never matches `null`." Java 21 distinguishes between a **type pattern used directly in `instanceof`** and an **unconditional type pattern inside a record pattern's component list**.

For example:

```java
record Address(String city) {}
Object input = new Address(null);
```

With the static component `String city`, the pattern:

```java
input instanceof Address(String city)
```

**can match** even when the `city` component is null. In the Java 21 JLS, a type pattern directly in a record component position that is **unconditional for the component's type** is *null-matching*. The pattern variable can be bound to `null`.

In contrast:

```java
Object input = null;
input instanceof Address(var city)
```

is `false`, because **the record reference itself** is null. A record pattern does not match a null record reference.

And:

```java
Object value = null;
value instanceof String s
```

is also `false` with direct `instanceof`.

Therefore, in `MissingComponentDemo`, the first branch **intentionally has a guard**:

```java
when id != null && name != null && city != null
```

If you only write `Address(String city)` and assume every `city` is non-null, tests can catch that gap. **A successful record pattern match does not replace validation of reference components.**

Whether a component type pattern is null-matching depends on the component's static type and whether the pattern is unconditional. Do not assume every type pattern in every record accepts null; for example, a `String s` type pattern for a component declared as `Object` is a different case. See Java 21 JLS §14.30.1–§14.30.3.

## 6. Case Study B: Map Input Data Missing Required Fields

At the JSON/API boundary, we often do not have an `Invoice` yet. We might receive a structure equivalent to `Map<String, Object>`:

```java
{
    "id": "I-7",
    "cents": 500,
    "currency": "VND"
}
```

The snippet above is a **JSON data description**, not Java syntax. Some requests might omit the `"cents"` key completely; some might include the key with `null`; and some might pass the string `"500"` instead of a number.

In a `Map`, checking:

```java
map.get("currency") == null
```

**cannot distinguish** between two cases:

1. The map **does not contain the key** `"currency"`.
2. The map contains the key `"currency"` with a **`null` value**.

To distinguish them, you must check:

```java
map.containsKey("currency")
```

and then classify the value.

This detail is crucial if the API contract returns different error codes for `missing field` and `explicit null`. If the payload has already been deserialized directly into a record, the mapping library might have collapsed both cases into the same value depending on its configuration; therefore, inspect the schema or an intermediate representation if you need to preserve this distinction.

## 7. Strict Record Design: Compact Canonical Constructor

A record does not automatically ensure that `id` is non-blank, the amount is positive, or `currency` is valid. Placing validation in the compact canonical constructor ensures that every call to the canonical constructor **enforces the invariants**.

```java
record Invoice(String id, long cents, String currency) {
    Invoice {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("invalid:id");
        }
        if (cents <= 0) {
            throw new IllegalArgumentException("invalid:cents");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("invalid:currency");
        }
    }
}
```

This is a **type declaration snippet**. The compact constructor receives the component values as implicit parameters. When the constructor completes normally, Java assigns the corresponding component fields.

Benefits:

- `new Invoice(null, 500L, "VND")` is rejected.
- `new Invoice("I-7", 0L, "VND")` is rejected.
- `new Invoice("I-7", 500L, " ")` is rejected.
- Any code creating an `Invoice` via the canonical constructor shares the same set of invariants.

**Limitation:** If you receive JSON missing `"cents"`, the primitive `long` has no null value to represent "not provided." A mapper might default it to `0`, reject it early, or behave differently depending on configuration. Do not treat `0` as proof of a missing field: it could also be an explicitly provided but invalid value. When you need to distinguish them, validate the input data **before** constructing the record.

## 8. Runnable Example: Validate Payload Then Construct Record

The following program is a small standalone test that **requires no JSON library or JUnit**. It covers valid payloads, missing keys, keys with null, wrong types, and blank values.

Save as `PayloadDecoderDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class PayloadDecoderDemo {
    record Invoice(String id, long cents, String currency) {
        Invoice {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("invalid:id");
            }
            if (cents <= 0) {
                throw new IllegalArgumentException("invalid:cents");
            }
            if (currency == null || currency.isBlank()) {
                throw new IllegalArgumentException("invalid:currency");
            }
        }
    }

    static Invoice parse(Map<String, ?> payload) {
        Objects.requireNonNull(payload, "payload");

        if (!payload.containsKey("id")) {
            throw new IllegalArgumentException("missing:id");
        }
        if (!(payload.get("id") instanceof String id)) {
            throw new IllegalArgumentException("invalid:id-type");
        }

        if (!payload.containsKey("cents")) {
            throw new IllegalArgumentException("missing:cents");
        }
        if (!(payload.get("cents") instanceof Long cents)) {
            throw new IllegalArgumentException("invalid:cents-type");
        }

        if (!payload.containsKey("currency")) {
            throw new IllegalArgumentException("missing:currency");
        }
        if (!(payload.get("currency") instanceof String currency)) {
            throw new IllegalArgumentException("invalid:currency-type");
        }

        return new Invoice(id, cents, currency);
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected
                            + " actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    static void reject(
            String name, Map<String, ?> payload, String expected) {
        try {
            parse(payload);
            throw new AssertionError(
                    "Expected invalid input: " + name);
        } catch (IllegalArgumentException ex) {
            check(name, expected, ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Map<String, Object> good = new HashMap<>();
        good.put("id", "I-7");
        good.put("cents", 500L);
        good.put("currency", "VND");

        check("valid",
                "Invoice[id=I-7, cents=500, currency=VND]",
                parse(good).toString());

        Map<String, Object> missing = new HashMap<>(good);
        missing.remove("cents");
        reject("missing-cents", missing, "missing:cents");

        Map<String, Object> explicitNull = new HashMap<>(good);
        explicitNull.put("currency", null);
        reject("null-currency", explicitNull,
                "invalid:currency-type");

        Map<String, Object> wrong = new HashMap<>(good);
        wrong.put("cents", "500");
        reject("wrong-type", wrong, "invalid:cents-type");

        Map<String, Object> blank = new HashMap<>(good);
        blank.put("id", " ");
        reject("blank-id", blank, "invalid:id");

        System.out.println("ALL 5 PASS");
    }
}
```

Run:

```bash
javac --release 21 PayloadDecoderDemo.java
java PayloadDecoderDemo
```

**Expected stdout:**

```text
PASS valid
PASS missing-cents
PASS null-currency
PASS wrong-type
PASS blank-id
ALL 5 PASS
```

### Why These Tests Are Valuable

- **Valid:** The payload has all keys, correct data types, and satisfies invariants, so `Invoice` is created.
- **Missing:** `remove("cents")` removes the key completely, so `containsKey` detects `"missing:cents"`.
- **Explicit null:** The map has `"currency"` with a null value; `instanceof String` returns false and reports `"invalid:currency-type"`, without confusing it with a missing key.
- **Wrong type:** `"500"` is a string, not a `Long`, so it is rejected before reaching the constructor.
- **Business invalid:** `" "` is still a `String`, so it passes the type check but is rejected by the compact constructor as an invalid value.

`HashMap` is used because **it allows null values**. `Map.of(...)` in Java **does not allow null keys or values**, making it unsuitable for constructing this `explicit null` case.

**Example specification note:** The parser requires the monetary value to be a Java `Long`. A JSON library may map integers to `Integer`, `Long`, `BigInteger`, or another type depending on its configuration. In a real application, define the proper schema and numeric conversion strategy (including range/overflow/precision) instead of treating `instanceof Long` as a universal JSON rule. Here, strict type checking is chosen intentionally for demonstration.

## 9. Test Missing and Null as Two Separate Cases

Some tests only construct:

```java
new Invoice(null, 500L, null)
```

and check for an exception. That test **does not prove** the parser detects missing keys in a payload; the object is already being constructed with a call that provides all parameter positions.

With a `Map`, build separate fixtures:

```java
Map<String, Object> absent = new HashMap<>();
absent.put("id", "I-7");
absent.put("cents", 500L);
// No "currency" key.

Map<String, Object> presentNull = new HashMap<>();
presentNull.put("id", "I-7");
presentNull.put("cents", 500L);
presentNull.put("currency", null);
```

- `absent.containsKey("currency")` is `false`.
- `presentNull.containsKey("currency")` is `true`.
- `get("currency")` returns `null` in **both** cases.

If an API distinguishes between "field not sent" and "field sent as null to clear it," this is even more critical for **PATCH/update requests**. Do not rely solely on `Optional<String>` to represent all three states (**absent / sent as null / sent with value**) if the API must distinguish them precisely; `Optional.empty()` does not carry information about whether the key was present.

## 10. A `null` Record Component Is Not Necessarily a Compile Error

A common misconception is: "Records are immutable, so they cannot have null components." A record provides `private final` component fields and accessor APIs, but reference types can still hold `null` if the constructor does not validate them.

For example:

```java
record Draft(String title, String note) {}

Draft draft = new Draft("Hello", null);
System.out.println(draft.note()); // Prints null.
```

This is an **illustrative snippet inside a class/method**, not a standalone file. The presence of `final` does not imply non-null.

To protect the domain:

- If a component is **required**, validate it in the canonical constructor/factory.
- If a component is **optional**, document the `null` policy clearly or use a meaningful model, such as a value object for special states.
- If a `record` holds a mutable collection/map, the record is only **shallowly immutable**: you may need `List.copyOf` or `Map.copyOf` during initialization, after handling the null policy.

Do not mechanically wrap every record component in `Optional`. The design should reflect the domain and API contract, especially the distinction between missing and explicit null in external data.

## 11. Test Matrix for the Case Study

A thorough test suite can be based on the following table:

| ID | Scenario | Layer to test | Expected |
| --- | --- | --- | --- |
| T01 | All keys present, valid types, valid values | Payload + constructor | Creates `Invoice` |
| T02 | Missing `"id"` | Payload parser | `missing:id` |
| T03 | `"id": null` present | Payload parser | `invalid:id-type` |
| T04 | `"id": " "` | Constructor invariant | `invalid:id` |
| T05 | Missing `"cents"` | Payload parser | `missing:cents` |
| T06 | `"cents": null` | Payload parser | `invalid:cents-type` |
| T07 | `"cents": "500"` | Payload parser | `invalid:cents-type` |
| T08 | `"cents": 0L` | Constructor invariant | `invalid:cents` |
| T09 | Missing `"currency"` | Payload parser | `missing:currency` |
| T10 | `"currency": null` | Payload parser | `invalid:currency-type` |
| T11 | `"currency": ""` | Constructor invariant | `invalid:currency` |
| T12 | Nested `Address(null)` | Nested pattern | Incomplete-value handling branch |
| T13 | Nested `Customer(..., null)` | Nested pattern | `missing-address` branch |
| T14 | `Order(..., null)` | Nested pattern | `missing-customer` branch |
| T15 | Null `Order` selector | `switch` | `case null` |
| T16 | Constructor missing argument | Compile-negative | `javac` reports arity error |
| T17 | Record pattern missing component | Compile-negative | `javac` reports pattern arity error |

You do not need to write a separate method by hand for every row; **parameterized tests** can group inputs cleanly. However, each group must assert specific errors or outcomes rather than merely checking that it "does not crash."

## 12. Compile-Negative Tests: Exact Component Count Is a Static Constraint

Create a fixture file `BadRecordArity.java` with code that **intentionally fails to compile**:

```java
public class BadRecordArity {
    record Pair(String left, String right) {}

    public static void main(String[] args) {
        new Pair("only-left"); // Invalid: record requires 2 arguments.
    }
}
```

Run separately:

```bash
javac --release 21 BadRecordArity.java
```

**Expected:** `javac` exits with a non-zero exit code because the constructor requires two parameters. Do not include this fixture in the production source set.

A second fixture that also intentionally fails to compile:

```java
record Pair(String left, String right) {}

static void wrong(Object input) {
    if (input instanceof Pair(var left)) {
        System.out.println(left);
    }
}
```

This second snippet is **illustrative code inside a class** that already declares `Pair`; it is not a standalone file. A record pattern must have the **exact same number of component patterns** as the record class; `Pair(var left)` has only one pattern while the record has two components.

Valid syntax:

```java
if (input instanceof Pair(var left, var right)) {
    System.out.println(left);
}
```

Note that "ignoring a component" at the **usage logic** level is different from "omitting a component" at the **pattern arity** level. The compiler enforces arity and type compatibility; runtime tests enforce actual component values.

## 13. An Exhaustive `switch` Does Not Guarantee Valid Components

A sealed hierarchy can make a `switch` exhaustive over **record types**, but it **does not prove** that `String id` or nested `Address city` is non-null or non-blank.

For example:

```java
sealed interface PaymentResult permits Paid, Rejected {}

record Paid(String id, long cents) implements PaymentResult {}
record Rejected(String reason) implements PaymentResult {}
```

A `switch` covering both `case Paid(...)` and `case Rejected(...)` may be exhaustive, yet it can still encounter `new Paid(null, -1)` if the constructor does not validate.

Combine these layers:

1. **Domain invariants** in the record constructor/factory.
2. **Pattern `switch`** to branch by variant/shape.
3. **Boundary validation** to distinguish missing, explicit null, and wrong types in external data.
4. **Unit/integration tests** to verify both data errors and business logic.

`case null` handles a null selector in `switch`; it **does not replace** handling null components inside a valid record instance.

## 14. Role of `when` Guards for Missing Component Data

In `MissingComponentDemo`, the guard:

```java
when id != null && name != null && city != null
```

acts as a **consumer-side business condition**. It prevents labeling a record with incomplete component data as `"complete"`.

However, a guard should not be the **only line of defense** for domain invariants. If `Order` requires non-empty `Customer`, `Address`, and `city`, ideally the constructor/factory validates them before the record enters the domain.

Guards are useful when:

- The system reads **legacy data** that might be invalid.
- A DTO represents a partially filled form where null is intentionally allowed.
- The consumer needs to classify data to return user-friendly errors rather than failing immediately during parsing.

**Be careful with guards:** a `case` with a `when` clause **does not cover the entire subtype**. You need an unguarded fallback case below it if the `switch` expression requires exhaustiveness. Do not simply add `default -> "unknown"` and hide the reason data is missing.

## 15. Testing Data Deserialized from JSON

How JSON maps to a record depends on the library: Jackson, Gson, JSON-B, framework binding, or custom serializers **do not necessarily** handle missing fields the same way. A mapper might:

- Pass `null` for reference components absent from the payload.
- Use default values for primitive components when fields are missing, or throw an error.
- Reject unrecognized properties.
- Apply validation annotations/configurations, or ignore them if not enabled.

**Do not assume** that "missing fields automatically throw `MissingComponentException`" or "records automatically return `Optional.empty`." The Java SE record mechanism does not prescribe the full behavior of JSON libraries.

If production uses a specific mapper, write integration tests at minimum for:

- A complete JSON object.
- JSON missing a required field.
- JSON with a field set to `null`.
- JSON with a field of the wrong type.
- Malformed or out-of-range numeric primitives.
- Missing nested object and `null` nested object.
- Property ordering and unknown properties if relevant to the contract.

Tests should record **the mapping library version and configuration**; never replace an integration test with assumptions based on the library's name.

## 16. Schema Evolution: Adding Components Can Affect Old Data

Suppose an older domain version had:

```java
record Customer(String name) {}
```

The new version adds a component:

```java
record Customer(String name, String email) {}
```

In Java source, `new Customer("An")` **does not remain valid** after changing the record unless an additional constructor is provided. Design an explicit migration: add a delegating constructor with an **intentional** default, update callers, or introduce a separate compatibility DTO.

Source-level migration example:

```java
record Customer(String name, String email) {
    Customer(String name) {
        this(name, "unknown@example.invalid");
    }
}
```

This is an **illustrative snippet**, not a real email address to contact. A default is only appropriate when business policy allows that state; do not invent arbitrary placeholder values for personal or binding business data.

For stored data or legacy JSON without `"email"`, you still need schema versioning or an adapter. A single-parameter constructor in Java **does not guarantee** that every JSON mapper will automatically pick that overload without proper configuration.

Changing a record's component list can also affect its canonical constructor signature, accessors, and record patterns in consumers. Therefore, maintain source compile tests, integration tests for both old and new data, and a rollout plan.

## 17. Distinguishing Accessor Errors from Missing Data Errors

A record pattern retrieves component values through the corresponding accessors. In Java 21, if an accessor is overridden and throws an exception during deconstruction, pattern matching can complete abruptly with a **`MatchException`** wrapping the cause. This differs from:

- Null component data where the pattern can still match.
- A null nested record reference where the nested record pattern does not match.
- A constructor rejecting invalid data with `IllegalArgumentException`.

If a project uses custom record accessors with side effects, test exceptions and observability separately; do not lump every failure under "missing component." For domain records, keep accessors simple and place validation in constructors/factories to avoid unpredictable deconstruction logic.

## 18. Missing Data in PATCH Requests Differs from Record Snapshots

An `Invoice(String id, long cents, String currency)` record typically represents a **complete snapshot of a value**. However, a PATCH request may only send the fields to be updated:

```json
{ "currency": "USD" }
```

In a PATCH context, "missing `id`/`cents`" can be **valid because they are not being modified**, rather than indicating invalid invoice data.

Do not immediately reuse the `Invoice` record as a PATCH DTO if it enforces that every field must be present. You can build an `InvoicePatch` using a **three-state model** per field: not sent, sent as null, or sent with a value. Upon receiving a patch, the system merges it with the existing domain object, validates the new record, and then persists it.

Using `Optional<T>` does not automatically solve these three states. `Optional.empty()` still needs to be distinguished from "property absent in payload" if the contract allows explicit null to mean "clear field."

Therefore, **missing-component tests must match the API context**: a missing field in a CREATE command may be an error, whereas a missing field in a PATCH may be normal.

## 19. Code Review and Testing Checklist

- [ ] Have you distinguished record constructor arity from missing fields in a payload?
- [ ] Have you tested **missing key** and **present-but-null** separately?
- [ ] Have you checked both wrong data types and type-valid values that violate invariants?
- [ ] For primitive components, have you explicitly handled the inability to represent null after mapping?
- [ ] Does the compact constructor/factory validate all required components?
- [ ] Are there unit tests for null nested record references, null components, and null selectors?
- [ ] Did you remember that an unconditional component type pattern **can match null**?
- [ ] Does every `when` guard have true/false tests and an appropriate fallback branch?
- [ ] Does the production JSON mapper have integration tests under its **actual version/config**?
- [ ] Is there a migration/fallback plan for legacy data when adding or changing record components?
- [ ] Have you separated full CREATE payloads from partial PATCH payloads?
- [ ] If using `Map.of`, have you avoided putting null into it when creating null-case fixtures?
- [ ] Have compile-negative tests been separated from the production source build?

**Conclusion:** A record enforces **component count and types at compile time**; it does not automatically fix missing payload fields, null references, or invalid business values. Good testing separates missing/null/wrong-type cases, uses constructors to enforce invariants, uses record patterns with careful guards and fallbacks, and verifies boundary mappers with realistic data. With Java 21 nested record patterns, especially do not assume that every component type pattern excludes null.

## Official References

- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 JLS §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java SE 21 JLS §14.30 — Patterns, null-matching, unconditional patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 JLS §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
