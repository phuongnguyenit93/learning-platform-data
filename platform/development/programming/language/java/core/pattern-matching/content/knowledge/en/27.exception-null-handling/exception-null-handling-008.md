# Designing Null Contracts for Domain Types in Java 21

## 1. Why is a null contract a domain design decision?

In Java, a reference can hold the value `null`, but **the fact that Java allows null does not mean the domain allows null**. An `Order` type with `customerId == null`, `destination == null`, or `amount <= 0` can be a meaningless state for the business. Conversely, an incomplete input request may be valid when `city` has not yet been provided.

A **null contract** is the commitment that a data type or API publishes: which fields are required to have a value, which fields may be absent, what absence means, what happens if it is violated, and which layer is responsible for handling it.

For example, consider a record:

```java
record Address(String city) {}
record Order(String id, Address address) {}
```

The syntax above **does not automatically forbid**:

```java
new Order(null, null);
```

Even though the components have types `String` and `Address`, the default canonical constructor adds no validation. Furthermore, a `record` only has **shallow immutability**: a final reference does not guarantee that every object it references is immutable.

When using **record patterns** and **pattern matching for `switch`**, the null contract determines whether a branch matches, whether a `when` guard is evaluated, and whether a fallback branch is needed. A poorly designed contract can cause unexpected `NullPointerException`s, `case` branches that never execute, or missing data being mistaken for valid data.

This article focuses on three strategies: **rejecting null for required data; accepting intentional absence at the boundary; and representing choice/absence with explicit domain types**. We then connect them to how pattern checks and exceptions work in Java.

**Versions:** `record` has been standard since Java 16; `instanceof` type patterns have been stable since Java 16; **record patterns (JEP 440)** and **pattern matching for `switch` (JEP 441)** have been standard since **Java 21**. The sample program uses JDK 21+ and does not require `--enable-preview`.

## 2. Four questions to answer for each component

Before declaring a domain type, make a table:

| Question | Example with an order | Decision to state explicitly |
| --- | --- | --- |
| Is the value required? | `customerId` | Required, null not accepted |
| Does absence have its own meaning? | Delivery address when the customer picks up at the counter | Do not use ambiguous null; can use a Pickup variant |
| If present, what counts as valid? | Non-empty customer ID, positive amount | Normalize and validate in the constructor |
| What if the contract is violated? | `new Order(null, ...)` | Throw an exception early; do not create a half-valid domain object |

A good contract must be applied consistently at:
- **Constructor/factory:** is the created object valid?
- **Accessor/method:** can the result be null or not?
- **Boundary API:** what is external input allowed to omit?
- **Pattern matching:** which branches handle missing data, and which branches assume invariants?
- **Tests:** how are null cases accepted or rejected?

Do not rely on an informal convention like "everyone knows this field is never null" instead of constructors, types, documentation, and tests.

## 3. Strategy 1 — Fail fast: reject null at domain invariants

For **required** data, the clearest approach is usually to reject it as soon as the value object is constructed:

```java
record CustomerId(String value) {
    CustomerId {
        value = java.util.Objects.requireNonNull(
            value, "customerId").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                "customerId must not be blank");
        }
    }
}
```

The **compact canonical constructor** receives parameters with the same names as the components. Reassigning the `value` parameter for normalization is allowed; when the constructor completes normally, Java assigns the processed value to the corresponding final field.

The contract of `CustomerId` in this example:

1. Null argument → `NullPointerException` with message `customerId`.
2. Empty or whitespace-only string → `IllegalArgumentException`.
3. String with leading/trailing whitespace → normalized via `strip()`.
4. After successful construction, `value()` is a non-null, non-empty string.

**Choose the exception type according to the contract**, not because a single choice is mandatory for every application. `Objects.requireNonNull` is commonly used to assert a required reference and throw `NullPointerException`. `IllegalArgumentException` is suitable for a value that is present but violates the allowed domain. For domains that need structured error messages, a dedicated exception or domain result can be used, but the policy must be consistent and documented.

For other required references:

```java
record Shipment(CustomerId customerId, Address destination) {
    Shipment {
        java.util.Objects.requireNonNull(customerId, "customerId");
        java.util.Objects.requireNonNull(destination, "destination");
    }
}
```

In objects constructed through this constructor, `shipment.customerId()` and `shipment.destination()` are always non-null. Processing methods do not need to repeat null-checks just to compensate for an invariant that already holds.

**Note:** this does not mean every `Shipment` received from any serialization mechanism or framework automatically preserves the contract without inspection. Check how your library reconstructs objects and the data paths at the boundary.

## 4. Strategy 2 — Absence is allowed, but its meaning must be defined

Some data is **truly optional**. For example, a user's contact phone number:

```java
record Contact(String email, String phone) {
    Contact {
        email = java.util.Objects.requireNonNull(
            email, "email").strip();
        if (email.isEmpty()) {
            throw new IllegalArgumentException("email is blank");
        }
        // Example contract: phone may be null, meaning not yet provided.
    }
}
```

Here, `phone == null` is **not a bug** if the public contract clearly states that it means "phone number not provided". However, callers must remember to check before using it:

```java
String phone = contact.phone();
if (phone != null && !phone.isBlank()) {
    System.out.println("Có số: " + phone);
}
```

On the other hand, null can propagate far and force multiple layers to perform checks. For domains with many absence scenarios or cross-field constraints, a type that represents the state explicitly is often better.

### How should `Optional` be used?

`Optional<T>` helps express **a result that may be absent**, for example:

```java
static java.util.Optional<String> findPhone(Contact contact) {
    return java.util.Optional.ofNullable(contact.phone());
}
```

Callers can use `ifPresent`, `orElse`, `map`, or `isPresent`. However, `Optional` **does not automatically make components inside a record non-null**, nor should it be treated as mandatory for every field. An `Optional` reference itself can still be null if validation is missing; `Optional.empty()` is what represents explicit absence.

For domain models, consider the API and frameworks: `Optional` is usually useful as a **return type**, while components/fields should be decided based on the contract, serialization, and how state is modeled. If "not yet present" is a distinct business state, sealed variants can be used as shown in the next section.

## 5. Strategy 3 — Replace ambiguous null with domain variants

Consider an order: home delivery needs an **address**, while counter pickup needs a **branch code**. Declaring:

```java
record Order(String id, Address deliveryAddress,
             String pickupBranch) {}
```

creates confusing combinations: both null, both populated, or only one populated. Every processing site must remember "exacty one of the two is allowed to be non-null".

A more explicit model:

```java
sealed interface Destination permits ShipTo, CollectAt {}

record ShipTo(Address address) implements Destination {
    ShipTo {
        java.util.Objects.requireNonNull(address, "address");
    }
}

record CollectAt(String branchCode) implements Destination {
    CollectAt {
        branchCode = java.util.Objects.requireNonNull(
            branchCode, "branchCode").strip();
        if (branchCode.isEmpty()) {
            throw new IllegalArgumentException("branchCode is blank");
        }
    }
}
```

Now a valid `Destination` is either **ShipTo** or **CollectAt**. Each variant's constructor maintains its own invariant, instead of forcing `Order` to guess based on pairs of nulls.

Benefits:
- Business meaning appears in the **type name**, not hidden in null.
- Impossible to create a "delivery without an address" state through `ShipTo`'s canonical constructor.
- A `switch` over the sealed hierarchy can check exhaustiveness of the variants at compile time.
- When adding `LockerPickup`, for instance, dispatching code can be flagged by the compiler to update.

However, **do not force every optional field into a sealed hierarchy**. A simple nullable phone may suffice if the contract is clear. Choose dedicated types when absence entails distinct behavior, invariants, or business branching.

## 6. Null semantics in pattern matching

### 6.1. `instanceof` with a null selector

```java
Object value = null;
if (value instanceof String text) {
    System.out.println(text.length()); // Does not run.
}
```

`null` does not match the type pattern `String text`; `instanceof` returns `false`. The variable `text` is only in scope where the compiler guarantees the pattern has matched.

### 6.2. `switch` needs an explicit policy for a null selector

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Đầu vào null";
        case String s -> "Chuỗi: " + s;
        default -> "Kiểu khác";
    };
}
```

In a pattern-matching `switch`, **`case null`** handles a null selector. Do not assume `default` always catches null: without an appropriate null case, a null selector can cause a `NullPointerException` according to enhanced switch rules. Null handling should be designed explicitly per the API contract, not "left to default later".

### 6.3. `var` in a record pattern can receive a null component

```java
record RawAddress(String city) {}

if (value instanceof RawAddress(var city)) {
    // city has type String, but it can still be null.
    System.out.println(city == null ? "(chưa có)" : city);
}
```

The record pattern `RawAddress(var city)` requires the outer **RawAddress** object to be non-null, but `var city` receives the component's value, even when it is null. **The static type String does not guarantee non-null**.

Compare with a nested pattern:

```java
record Customer(RawAddress address) {}

// address must be a non-null RawAddress to match.
if (value instanceof Customer(RawAddress(var city))) {
    // city can still be null.
    System.out.println(city);
}
```

If `Customer.address() == null`, the nested `RawAddress(...)` does not match, so **the entire `Customer(...)` does not match**. No subsequent guard is invoked for that branch.

### 6.4. `when` guards are evaluated after the pattern matches

```java
// Illustrative case label inside a suitable switch.
case RawAddress(var city) when city != null && !city.isBlank() ->
    "Thành phố: " + city;
```

The outer pattern must match first, and then the guard checks the component. `city != null` comes **before** `!city.isBlank()` to avoid an NPE thanks to short-circuiting of `&&`. A false guard causes the `switch` to consider the next branch, rather than reporting a validation error by itself.

If the record constructor already **forbids null and blank**, this guard may be redundant for instances built under that contract. Even so, guards remain useful for **context-dependent rules**, such as allowing only certain delivery cities.

## 7. Distinguishing three situations: failed match, failed guard, failed constructor

| Situation | Example | Consequence |
| --- | --- | --- |
| **Constructor rejects** | `new ShipTo(null)` | Throws NPE immediately at construction; no valid `ShipTo` exists |
| **Pattern does not match** | `Customer(RawAddress(...))` when `address == null` | Branch is not selected, guard does not run |
| **Pattern matches but guard is false** | `RawAddress(var city) when city != null` with `city == null` | Branch is not selected; other branches are considered |
| **Pattern matches and guard is true** | `RawAddress("Huế")` with nonblank guard | Executes branch body |
| **Null `switch` selector** | `switch (null)` without appropriate null handling | May throw NPE; must design `case null` or reject beforehand |
| **Using a nullable reference unchecked** | `city.isBlank()` when `city == null` | NPE when executing the call |

These are distinct mechanisms. **Do not use a pattern/guard as a substitute for constructor invariants**, and do not treat every exception as a "failed match".

## 8. Boundaries: raw data vs. validated domain objects

An input DTO (JSON, form, message queue) often contains **incomplete or untrusted** data. Domain types should be created **after validation and normalization**.

```text
Input HTTP / JSON / file
        |
        v
Raw DTO (may have missing fields, null, blank)
        |
        v
Parse + Validate + Normalize
        |
        +--> Input error / Explicit error Result
        |
        v
Domain value objects (invariants protected)
        |
        v
Business rules / pattern matching / persistence
```

For example:
- `RawOrder` with `customerId == null`: represents missing input; the receiver can return a 400 error with a list of fields (depending on the protocol).
- A successfully constructed `CustomerId`: non-null, non-blank; domain code can rely on the invariant.
- `Destination` is one of two clear variants: no need to guess "what should we do if both address and branch code are null?".
- When the contract requires structured error responses, validation exceptions should be converted into API-policy responses at the boundary. Do not return stack traces or internal details directly to clients.

**Avoid both accepting null in a domain constructor and silently turning it into an empty string or a fake ID.** Doing so hides bad data, preventing downstream logic from distinguishing "missing" from "real value".

## 9. Complete Java 21 program: contracts, nested patterns, and null

Create the file **`DomainNullContractDemo.java`**:

```java
import java.util.Objects;

public class DomainNullContractDemo {

    // Raw DTO intentionally unvalidated: null is data to be checked.
    record RawOrder(String customerId, String city) {}

    record CustomerId(String value) {
        CustomerId {
            value = Objects.requireNonNull(
                value, "customerId").strip();
            if (value.isEmpty()) {
                throw new IllegalArgumentException(
                    "customerId must not be blank");
            }
        }
    }

    record Address(String city) {
        Address {
            city = Objects.requireNonNull(city, "city").strip();
            if (city.isEmpty()) {
                throw new IllegalArgumentException("city is blank");
            }
        }
    }

    sealed interface Destination permits ShipTo, CollectAt {}

    record ShipTo(Address address) implements Destination {
        ShipTo {
            Objects.requireNonNull(address, "address");
        }
    }

    record CollectAt(String branchCode) implements Destination {
        CollectAt {
            branchCode = Objects.requireNonNull(
                branchCode, "branchCode").strip();
            if (branchCode.isEmpty()) {
                throw new IllegalArgumentException(
                    "branchCode is blank");
            }
        }
    }

    record Order(CustomerId customerId,
                 Destination destination,
                 long amount) {
        Order {
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(destination, "destination");
            if (amount <= 0) {
                throw new IllegalArgumentException(
                    "amount must be positive");
            }
        }
    }

    // At the boundary: a var pattern can receive a null component.
    static String inspectRaw(Object value) {
        return switch (value) {
            case null -> "Raw: null";

            case RawOrder(var id, var city)
                    when id == null || id.isBlank() ->
                "Raw: thiếu khách";

            case RawOrder(var id, var city)
                    when city == null || city.isBlank() ->
                "Raw: thiếu thành phố";

            case RawOrder(var id, var city) ->
                "Raw: " + id.strip() + "/" + city.strip();

            default -> "Raw: sai kiểu";
        };
    }

    // In the domain: constructors already protect nested components.
    static String route(Object value) {
        return switch (value) {
            case null -> "Order: null";

            case Order(
                    CustomerId(var id),
                    ShipTo(Address(var city)),
                    var amount)
                    when amount >= 1_000 ->
                "Ưu tiên: " + id + " -> " + city;

            case Order(
                    CustomerId(var id),
                    ShipTo(Address(var city)),
                    var amount) ->
                "Giao: " + id + " -> " + city;

            case Order(
                    CustomerId(var id),
                    CollectAt(var branchCode),
                    var amount) ->
                "Nhận: " + id + " @ " + branchCode;

            default -> "Order: sai kiểu";
        };
    }

    public static void main(String[] args) {
        System.out.println(
            inspectRaw(new RawOrder(null, "Huế")));
        System.out.println(
            inspectRaw(new RawOrder(" C-9 ", null)));
        System.out.println(
            inspectRaw(new RawOrder(" C-9 ", " Huế ")));
        System.out.println(inspectRaw(null));

        CustomerId customerId = new CustomerId(" C-9 ");
        Address address = new Address(" Huế ");

        System.out.println(route(new Order(
            customerId, new ShipTo(address), 1_500)));

        System.out.println(route(new Order(
            customerId, new ShipTo(address), 500)));

        System.out.println(route(new Order(
            customerId, new CollectAt(" Q1 "), 200)));

        System.out.println(route(null));
        System.out.println(route(new RawOrder("X", "Huế")));

        try {
            new Order(customerId, null, 100);
        } catch (NullPointerException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }

        try {
            new CustomerId("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối mã khách rỗng");
        }
    }
}
```

Compile and run with **JDK 21+** in the directory containing the file:

```bash
javac --release 21 -encoding UTF-8 DomainNullContractDemo.java
java DomainNullContractDemo
```

Expected output:

```text
Raw: thiếu khách
Raw: thiếu thành phố
Raw: C-9/Huế
Raw: null
Ưu tiên: C-9 -> Huế
Giao: C-9 -> Huế
Nhận: C-9 @ Q1
Order: null
Order: sai kiểu
Từ chối: destination
Từ chối mã khách rỗng
```

### 9.1. Why doesn't raw data throw an exception immediately?

`RawOrder` is a DTO at the boundary. In this example, the default constructor allows `null`; `inspectRaw` interprets it as a missing-field error. The branch `case RawOrder(var id, var city)` still matches a raw record with null components, thanks to `var`. Because the first two guards handle null/blank, the general `RawOrder` branch only receives the remaining data.

The first guard branch takes precedence if **both id and city are missing**. This is a **first-error classification policy**, not a conclusion that the system only has one error. An API that wants to return a list of all errors should use aggregate validation rather than a single `switch` returning a string.

### 9.2. Why doesn't the domain need to repeat every null guard?

`CustomerId`, `Address`, `ShipTo`, `CollectAt`, and `Order` are designed with clear invariants. Once the constructors succeed, code using `route` can rely on the required values being present.

The branch `Order(CustomerId(var id), ShipTo(Address(var city)), var amount)` can only match when both `Order → CustomerId` and `Order → ShipTo → Address` match their respective records. For instances created through constructors with invariants, these layers are non-null. The guard `amount >= 1000` is a **context-specific business rule**, distinct from the `amount > 0` invariant protected by the constructor.

**Note:** `case null` in `route` is still meaningful when **the input variable passed to `route` itself is null**, even though `Order`'s constructor forbids null components.

### 9.3. Why is `CollectAt` better than a null address?

If the customer picks up at the counter, the needed information is `branchCode`. With the sealed variant `CollectAt`, there is no need to pass `ShipTo(null)` and explain "null means counter pickup". The domain structure directly expresses the behavior:

- `ShipTo(Address)`: has a delivery address.
- `CollectAt(String branchCode)`: has a pickup branch.
- `Order.destination`: must be one of those variants.

This reduces the number of invalid state combinations and makes `switch` easier to keep exhaustive.

### 9.4. Distinguishing exceptions from classification results

`new Order(customerId, null, 100)` throws `NullPointerException("destination")` **before a valid `Order` exists**. No branch of `route` handles it because the record was never successfully constructed. This is fail-fast behavior per the constructor contract.

`route(new RawOrder(...))` does not throw an exception; it returns `"Order: sai kiểu"` via `default` because a selector of type `Object` can be another type. This is input handling at the boundary, not a constructor error.

## 10. Choosing exception, result, or null: one contract per API

| Case | Typically suitable design | Reason |
| --- | --- | --- |
| Value object constructor with a null required field | `Objects.requireNonNull` or a defined validation error | Fail fast, preserve invariants |
| Non-null value with invalid format/range | `IllegalArgumentException` or domain validation error | Distinguish "missing" from "present but invalid" |
| Lookup that may find no result as a normal case | `Optional<T>`, typed result, or dedicated state type | Avoid treating normal absence as an exception |
| Business domain with mutually exclusive valid variants | `sealed interface` with record/class variants | Represent states in the type system |
| Unvalidated input from HTTP/JSON | Nullable raw DTO + validate/parse step | Collect user-friendly errors at the boundary |
| Function encounters an unrecoverable invariant violation | Contract exception or structured error result | Avoid continuing with invalid state |
| Field that may be absent without distinct behavior | Documented nullable field, or optional return | Keep the model simple if clear enough |

**Distinguish programming errors from normal business situations.** Violating a required `Order.destination` indicates the caller passed invalid data. "No nearby delivery address found" may be a normal situation needing an absence result type, not necessarily throwing an NPE.

It is discouraged to **broadly catch `NullPointerException`** to turn every null into a "missing data" result. Doing so can mask other bugs such as unexpected null dereferences. Validate at the boundary or in constructors, and catch exceptions at a layer that knows how to translate them into valid responses.

## 11. How the null contract affects case order and exhaustiveness

For a `switch` with multiple patterns, case order still matters. For example:

```java
// Illustration in a switch receiving Object:
case RawOrder(var id, var city) when id == null ->
    "Thiếu id";
case RawOrder(var id, var city) ->
    "RawOrder còn lại";
```

The guarded branch must precede the general branch. Writing it in reverse:

```java
// INTENTIONALLY DOES NOT COMPILE: guarded case is dominated.
case RawOrder(var id, var city) -> "Mọi RawOrder";
case RawOrder(var id, var city) when id == null -> "Thiếu id";
```

The first `RawOrder(...)` branch covers every non-null `RawOrder` value, so the later branch has no chance of ever being selected.

If a `switch` receives a **sealed type**, type patterns covering all permitted subclasses can make a `switch` expression exhaustive without `default`. However:
- Arbitrary guards cannot replace a general branch when values of the same type may fail the guard.
- Handling null for the selector is a separate policy.
- An overly broad `default` can hide a missing handler for a new subtype when the sealed hierarchy changes.

In particular, do not try to handle a null component with `when` if **a nested record pattern has already failed at that level**. To catch a null component, deconstruct at a shallower level with `var` and then check it.

## 12. Null cases in collections and generic domain types

### 12.1. `List.copyOf` does not accept null elements

```java
record OrderLines(java.util.List<String> lines) {
    OrderLines {
        lines = java.util.List.copyOf(
            java.util.Objects.requireNonNull(lines, "lines"));
    }
}
```

`List.copyOf` creates an unmodifiable list and rejects null elements. It protects the **list structure**, not turning mutable elements into immutable ones. Therefore, when designing a null contract for collections, decide: can the collection be null, can elements be null, is empty valid, and can mutable elements be shared?

### 12.2. `Map.get` does not distinguish missing key from mapped null

```java
String value = map.get(key);
if (value == null) {
    // Either the key is absent, or the key exists with a mapped value of null.
}
```

For `Map` implementations that allow null values, use `containsKey` if you need to distinguish the two cases. For maps that disallow null (such as some unmodifiable maps), the contract changes. Do not assume that a null returned from an API always carries a single meaning.

### 12.3. Do not confuse non-null types with runtime checks

Java does not enforce a unified non-null type checking system for every reference just because a field is declared as `String`. Annotations such as `@NonNull` or `@Nullable` can assist tooling/IDEs/static analyzers, but annotation names, coverage, and whether runtime checks occur depend on the libraries/tools in use. For critical invariants, validate in constructors/factories and test actual behavior.

## 13. Process for reviewing a null contract

When reviewing a domain type and the patterns that use it:

1. **List components** and mark each as: required, may be absent, or should be a separate type variant.
2. **Define absence:** does null mean unknown, not applicable, not yet entered, or error? If it has multiple meanings, null may be too ambiguous.
3. **Check constructors/factories:** is null rejected at the right time; are non-null values valid; is there arbitrary normalization?
4. **Inspect the boundary:** raw DTOs may accept null, but is there a conversion/validation step before creating domain objects?
5. **Inspect patterns:** at which component can a record pattern at each level fail due to null; which `var` can hold null?
6. **Inspect guards:** are they null-safe, short-circuiting, and avoiding method calls on nullable variables before checking?
7. **Inspect switch selectors:** is null handled explicitly, and do default/exhaustiveness match the contract?
8. **Inspect error results:** throwing exceptions, returning `Optional`, or a domain `Result`; can callers distinguish important situations?
9. **Test** null cases, blank cases, valid data, boundary values, missing variants, and nested pattern failures.
10. **Re-read the API:** can a user infer the contract purely from types, names, and documentation without tracing every call site?

In real systems, also check serialization, ORM, collection copying, thread-safety, and how static analysis tools process annotations. These are integration concerns that are not solved merely by adding `case null`.

## 14. Common mistakes and how to fix them

| Mistake | Risk | How to fix |
| --- | --- | --- |
| Assuming `record` automatically forbids null components | Meaningless domain states can be created | Compact constructor with validation |
| Allowing null on every component "for flexibility" | Increases check branches and invalid state combinations | Distinguish required vs. optional vs. variant |
| Using null to represent multiple different states | Callers do not know the meaning | Use enums/sealed variants or named results |
| Assuming `var city` is always non-null in a record pattern | Calling `isBlank()` causes NPE | Check null first |
| Assuming a guard null check catches a null nested record | Sub-pattern fails before the guard | Stop deconstruction at a shallower level |
| Assuming `default` automatically catches a null selector | Runtime may throw NPE | Use `case null` or reject null before the switch |
| Catching all NPEs and treating them as missing input | Masks unintended dereference bugs | Validate at boundaries and constructors |
| Putting `Optional` on every field indiscriminately | Hard for APIs/frameworks; Optional reference can still be null | Choose return types/variants per contract |
| Assuming final fields guarantee deep immutability | Nested collections/objects can still mutate | Defensive copies and immutable components |
| Using type patterns to replace validation | Patterns only check structure/types | Place invariants and business rules at the right layer |
| Placing a general branch before a guarded case | Dominance; specific case becomes unreachable | Place guarded cases first |
| Exception messages containing sensitive data | Data leakage when returning errors to callers | Filter error details at the API boundary |

## 15. Practice exercises

**Exercise 1 — Designing a required field.** Write `record ProductCode(String value)` that rejects null and blank strings, and trims whitespace. Predict the exceptions for `new ProductCode(null)` and `new ProductCode("  ")`.

**Exercise 2 — Null at different levels.** With `Customer(RawAddress(var city))`, explain the difference between `Customer(null)` and `Customer(new RawAddress(null))`. Answer: the first **does not match the nested pattern**; the second **matches with `city == null`**.

**Exercise 3 — Raw DTO.** Run `DomainNullContractDemo.java`, adding `new RawOrder(null, null)`. Predict which branch is selected. Answer: **`Raw: thiếu khách`** because the id guard comes first. If both errors need to be reported, replace the string-returning mechanism with a collection of validation errors.

**Exercise 4 — Sealed variant.** Add `record Locker(String lockerCode) implements Destination`, validate that the code is non-null/non-blank, update `permits`, and add the corresponding case in `route`. Explain why the new type is better than a convention where `destination == null` means locker pickup.

**Exercise 5 — Fail-fast constructors.** Write tests for `new ShipTo(null)`, `new CollectAt(" ")`, `new Order(customerId, null, 100)`, and `new Order(customerId, destination, 0)`. Distinguish `NullPointerException` and `IllegalArgumentException` according to the demo contract.

**Exercise 6 — Guards and null-safety.** Compare `city != null && !city.isBlank()` with `city == null || city.isBlank()`. Why are both safe due to short-circuiting, yet express opposite meanings?

**Exercise 7 — Verifiable contract change.** Suppose the delivery address can be temporarily missing in a Draft state. Would you modify `ShipTo` to accept null, create a `PendingAddress` variant, or separate `DraftOrder` and `ConfirmedOrder`? Explain the impact on invariants, processing flows, and pattern matching.

## 16. Summary

**Designing the null contract of domain types must come before writing pattern matching.** A non-null component protected in the constructor reduces the need for repeated guards. An absence with business meaning should be expressed explicitly—via a documented nullable contract, `Optional` at appropriate APIs, or sealed type variants when the state has distinct behavior.

Key takeaways:
- `record` helps represent data, but **does not automatically forbid null** and does not automatically provide deep immutability.
- `Objects.requireNonNull` is usually suitable for required references; other validation protects the domain of non-null values.
- `var` in a record pattern can hold a null component; **nested record patterns require the inner record to be non-null**.
- `case null` expresses the policy for the `switch` selector; `when` is only evaluated after the pattern has matched.
- Distinguish **constructor rejection**, **pattern non-match**, **false guard**, and **runtime NPE**.
- Clearly separate **raw input → validation → domain object**; do not let ambiguous nulls spread throughout the domain.

### References

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String))
- [Java SE 21 — Optional](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
