# Summary of Deconstruction in the Domain — Record Case Study with Java Pattern Matching

In a domain model, structured data is often represented by multiple small **records**: an address holds a city and a country, a customer has a delivery address, and an order holds a customer and a total amount. **Record deconstruction** lets you check that an object has the exact record shape you need while extracting its components into clearly typed variables. Since **Java 21**, you can write record patterns such as `Customer(var id, Address(var city, var country))` in `instanceof` or `switch`.

However, **knowing how to write a nested record pattern is not enough to build a good domain model**. What you need to decide is: which fields data might still be missing, where invariants belong, when to use a pattern for classification, when to keep the object intact and call a domain-meaningful method, and when to separate input validation from a validated domain.

This article belongs to **Java Core Pattern Matching → Record Case Study**, covering **Summary of deconstruction in the domain**. We use a case study that processes order creation/cancellation requests, consisting of draft data `DraftOrder`, records `Customer`, `Address`, `Money`, and the sealed hierarchy `OrderAction`. The example shows how to combine record patterns, nested patterns, guards, fallbacks, exhaustive `switch`, and validation **without turning pattern matching into an automatic business framework**.

**Versions:** Records have been stable since Java 16 (JEP 395), sealed classes/interfaces since Java 17 (JEP 409), and record patterns and pattern matching for `switch` since **Java 21** (JEP 440, JEP 441). The two standalone programs below are written for **Java 21+** without needing preview features enabled.

## 1. What is deconstruction in a domain context?

Given the declarations:

~~~java
// Java 21+ snippet: records in the same appropriate scope.
record Address(String city, String country) {}
record Customer(String id, Address deliveryAddress) {}
~~~

A **type pattern** only checks the type and binds the entire object:

~~~java
// Snippet: input has type Object.
if (input instanceof Customer customer) {
    System.out.println(customer.id());
}
~~~

A **record pattern** both checks the record and binds its components in order:

~~~java
if (input instanceof Customer(var customerId, var address)) {
    System.out.println(customerId + ": " + address);
}
~~~

And a **nested record pattern** goes deeper:

~~~java
if (input instanceof Customer(
        var customerId,
        Address(var city, var country))) {
    System.out.println(customerId + " -> " + city + "/" + country);
}
~~~

In the last form:

1. `input` must be a matching `Customer`.
2. The record pattern reads the first component `id` into the variable `customerId`.
3. The second component `deliveryAddress` must match a non-`null` `Address`.
4. If it matches, the pattern continues extracting `city` and `country`.
5. If the `deliveryAddress` component is `null`, **the nested `Address(...)` does not match**; the `if` branch does not execute.

This is **pattern matching on data shape and component values**. It does not automatically verify that the delivery address was confirmed by the customer, that the customer is authorized to pay, or that the order ID is stored in the database.

### An easy-to-remember mental model: sum and product

A record such as `Address(String city, String country)` represents a **product type**: a value that simultaneously holds all declared components. A sealed hierarchy with subtypes `Submit` or `Cancel` describes a **sum type**, close to the idea of “one of the permitted variants”.

~~~text
OrderAction
    |
    +-- Submit(DraftOrder)
    |        |
    |        +-- orderId
    |        +-- Customer(id, Address(city, country))
    |        +-- Money(currency, cents)
    |
    +-- Cancel(orderId, reason)
~~~

The pattern `Submit(DraftOrder(...))` checks the **action variant**, and then the nested record patterns read the **data components** of that variant. This is a very natural combination when a domain has a closed set of actions with different payloads.

You do not need to use the terms “sum/product type” in every Java API; this mental model simply helps separate **selecting a variant** from **extracting structure**.

## 2. Why is modeling separate records better than “one record with every field”?

Suppose a service receives two kinds of requests: submitting an order and cancelling an order. A weak design might look like:

~~~java
// ANTI-PATTERN ILLUSTRATION, not recommended for internal domains.
record RequestData(
    String kind,
    String orderId,
    String customerId,
    String city,
    String country,
    Long amountCents,
    String cancelReason
) {}
~~~

This model allows:

- `kind = "CANCEL"` while still having `amountCents` and `city`.
- `kind = "SUBMIT"` while missing `customerId`.
- Misspelled or unsupported `kind` strings.
- `amountCents` being `null` when logic expects a primitive value.
- Many nullable fields where code must constantly guess which fields are valid in each state.

Instead of one payload containing everything, we use records with clear meanings:

~~~java
// Java 21+ snippet, within the same appropriate sealed hierarchy scope.
sealed interface OrderAction permits Submit, Cancel {}
record Submit(DraftOrder draft) implements OrderAction {}
record Cancel(String orderId, String reason) implements OrderAction {}
~~~

When handling `Submit`, the compiler knows the payload is `DraftOrder`; for `Cancel`, the compiler knows there are `orderId` and `reason`. Branching no longer relies on comparing `String kind` and casting the payload at runtime.

**However, sealed types and records do not replace data validation.** Callers can still construct `new Cancel(null, null)` if the constructor does not block it; and `new Submit(null)` is also valid at the type level when reference components are unchecked. Before passing a request into real business logic, you must determine the trust level and validate values.

## 3. Distinguishing draft data from a validated domain

In the case study, we intentionally use the name `DraftOrder` for data that **may be incomplete**:

~~~java
record DraftOrder(String orderId, Customer customer, Money total) {}
~~~

The word “Draft” makes it clear this is data being collected or normalized; it may lack `customer`, `total`, or another component. At system boundaries, we often encounter DTOs from HTTP/JSON, message brokers, or legacy data imports with varying levels of trust.

Conversely, a **validated domain object** should have a stricter contract:

~~~java
// Snippet inside a class with the types and helpers in the same scope.
record ConfirmedOrder(
        String orderId, Customer customer, Money total) {
    ConfirmedOrder {
        requireText(orderId, "orderId");
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(
                customer.deliveryAddress(), "deliveryAddress");
        java.util.Objects.requireNonNull(total, "total");
    }
}
~~~

Here, the compact constructor prevents most missing-data states at object creation time. If every `ConfirmedOrder` instance can only be created through this contract, processing code can rely on those invariants to simplify its checking flow.

**Important limitation:** Records and patterns do not automatically prove that data coming over the network has been fully authenticated or validated. Decoding JSON into records, checking authorization, order state, currency, inventory, and transactions remain the separate responsibility of the boundary/service layer.

### Practical rule

- **Boundary/draft:** components may still be missing; use deconstruction + fallback or a validation result to clearly indicate incomplete cases.
- **Validated domain:** constructors/factories already enforce invariants; there is no need to repeat null checks in every operation as long as the contract is genuinely upheld.
- **Business service:** orchestrates authorization, persistence, transactions, I/O, and side effects; do not put these actions into `when` guards or custom accessors.

Type names should tell the reader the level of trust. Do not call a payload that is still missing many fields `ConfirmedOrder` just because a record auto-generates a constructor.

## 4. Short example: nested patterns and `null` components

Before diving into the larger case study, let's confirm a rule that often causes confusion. Create the file **`RecordDeconstructionQuickDemo.java`**:

~~~java
public class RecordDeconstructionQuickDemo {
    record Location(String city) {}
    record Delivery(Location location) {}

    static String route(Object input) {
        return switch (input) {
            case Delivery(Location(var city)) -> "Send to " + city;
            case Delivery(var location) -> "No location";
            case null -> "Missing input";
            default -> "Not a delivery";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(new Delivery(new Location("Hue"))));
        System.out.println(route(new Delivery(null)));
        System.out.println(route(null));
        System.out.println(route("Other"));
    }
}
~~~

Run with JDK 21+:

~~~bash
javac --release 21 -encoding UTF-8 RecordDeconstructionQuickDemo.java
java RecordDeconstructionQuickDemo
~~~

Output:

~~~text
Send to Hue
No location
Missing input
Not a delivery
~~~

Exact breakdown of the four cases:

1. `new Delivery(new Location("Hue"))` matches both `Delivery(...)` and the nested `Location(...)`; `city = "Hue"`.
2. `new Delivery(null)` **does not match the nested record pattern** `Location(var city)`, but **matches `Delivery(var location)`**; the variable `location` receives `null`. Result: `"No location"`.
3. A `null` selector is handled by `case null`; it does **not** become `Delivery(null)`.
4. A `String` value is not a `Delivery`, so it reaches `default`.

**Three kinds of “null” to distinguish:** a null selector; a non-null record object with a null component; and an empty component such as `new Location("")`. Record patterns distinguish shape/type, not automatically turning empty strings into null. To forbid an empty city, you must validate or use an appropriate guard.

## 5. Designing the order case study before deconstructing

We use records with clear roles:

| Type | Role | Contract in the example |
| --- | --- | --- |
| `Address(city, country)` | Delivery address | `city`/`country` must not be null or blank |
| `Customer(id, deliveryAddress)` | Customer and intended address | `id` must have text; `deliveryAddress` may be null while a draft has not chosen a destination |
| `Money(currency, cents)` | Monetary amount in smallest unit | `currency` has text; `cents` is non-negative |
| `DraftOrder(orderId, customer, total)` | Not-yet-fully-validated order data | Components may be missing to illustrate fallback |
| `Submit(draft)` | Request to submit an order | One variant of `OrderAction` |
| `Cancel(orderId, reason)` | Request to cancel | The other variant |
| `OrderAction` | Closed set of actions | `sealed interface` permitting only two variants in the example |

**Why use `Money(currency, cents)` instead of `double amount`?** Integer smallest units avoid a class of floating-point rounding issues in currency. However, this sample does not yet check ISO currency codes, decimal places per currency, or addition overflow; a real payment system must design those invariants.

**Why can `Customer.deliveryAddress` be null?** The sample domain includes a draft step where a customer may not yet have selected a delivery address. If your system requires a `Customer` to always have an address, change the contract: enforce non-null in the constructor or separate `CustomerProfile` from `DeliveryDetails`. Allowing null here is **an intentional choice to teach deconstruction**, not a universal rule for every customer model.

**Why name them `Submit` and `Cancel` instead of `OrderSubmitted` and `OrderCancelled`?** These two types are **commands/requests** to be checked, not domain events confirming something already happened. Only after obtaining a result should the application layer emit an appropriate event according to system rules.

## 6. Complete Java 21+ program: domain deconstruction with fallback

Create the file **`DomainDeconstructionDemo.java`**:

~~~java
public class DomainDeconstructionDemo {
    sealed interface OrderAction permits Submit, Cancel {}

    record Address(String city, String country) {
        Address {
            requireText(city, "city");
            requireText(country, "country");
        }
    }

    record Customer(String id, Address deliveryAddress) {
        Customer {
            requireText(id, "customerId");
        }
    }

    record Money(String currency, long cents) {
        Money {
            requireText(currency, "currency");
            if (cents < 0) {
                throw new IllegalArgumentException("cents must be non-negative");
            }
        }
    }

    record DraftOrder(String orderId, Customer customer, Money total) {}

    record Submit(DraftOrder draft) implements OrderAction {}
    record Cancel(String orderId, String reason) implements OrderAction {}

    static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must be nonblank");
        }
    }

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String describe(OrderAction action) {
        return switch (action) {
            case Submit(DraftOrder(var orderId,
                    Customer(var customerId, Address(var city, var country)),
                    Money(var currency, var cents)))
                    when hasText(orderId) && cents >= 10_000 ->
                    "Review " + orderId + " for " + customerId
                            + " to " + city + "/" + country
                            + ": " + cents + " " + currency;

            case Submit(DraftOrder(var orderId,
                    Customer(var customerId, Address(var city, var country)),
                    Money(var currency, var cents)))
                    when hasText(orderId) ->
                    "Ready " + orderId + " for " + customerId
                            + " to " + city + "/" + country
                            + ": " + cents + " " + currency;

            case Submit(var draft) -> "Incomplete submit";

            case Cancel(var id, var reason)
                    when hasText(id) && hasText(reason) ->
                    "Cancel " + id + ": " + reason;

            case Cancel(var id, var reason) -> "Invalid cancellation";

            case null -> "Missing action";
        };
    }

    static String describeExplicit(DraftOrder draft) {
        if (draft == null || !hasText(draft.orderId())) {
            return "Incomplete submit";
        }

        Customer customer = draft.customer();
        Money total = draft.total();
        if (customer == null || customer.deliveryAddress() == null
                || total == null) {
            return "Incomplete submit";
        }

        Address address = customer.deliveryAddress();
        String prefix = total.cents() >= 10_000 ? "Review " : "Ready ";
        return prefix + draft.orderId() + " for " + customer.id()
                + " to " + address.city() + "/" + address.country()
                + ": " + total.cents() + " " + total.currency();
    }

    public static void main(String[] args) {
        Submit[] samples = {
            new Submit(new DraftOrder("O-100",
                    new Customer("C-7", new Address("Hue", "VN")),
                    new Money("VND", 12_500))),
            new Submit(new DraftOrder("O-101",
                    new Customer("C-8", new Address("Hanoi", "VN")),
                    new Money("VND", 500))),
            new Submit(new DraftOrder("O-102",
                    new Customer("C-9", null), new Money("VND", 800))),
            new Submit(new DraftOrder("O-103", null, new Money("VND", 800))),
            new Submit(new DraftOrder("  ",
                    new Customer("C-4", new Address("Da Nang", "VN")),
                    new Money("VND", 800))),
            new Submit(null)
        };

        for (Submit submit : samples) {
            String viaPattern = describe(submit);
            String viaAccessors = describeExplicit(submit.draft());
            System.out.println(viaPattern + " | equal="
                    + viaPattern.equals(viaAccessors));
        }

        System.out.println(describe(
                new Cancel("O-100", "Customer requested")));
        System.out.println(describe(new Cancel("O-100", "  ")));
        System.out.println(describe(null));

        try {
            new Money("VND", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid money: " + ex.getMessage());
        }

        try {
            new Address("", "VN");
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid address: " + ex.getMessage());
        }
    }
}
~~~

Compile/run commands:

~~~bash
javac --release 21 -encoding UTF-8 DomainDeconstructionDemo.java
java DomainDeconstructionDemo
~~~

Exact output:

~~~text
Review O-100 for C-7 to Hue/VN: 12500 VND | equal=true
Ready O-101 for C-8 to Hanoi/VN: 500 VND | equal=true
Incomplete submit | equal=true
Incomplete submit | equal=true
Incomplete submit | equal=true
Incomplete submit | equal=true
Cancel O-100: Customer requested
Invalid cancellation
Missing action
Invalid money: cents must be non-negative
Invalid address: city must be nonblank
~~~

### What the program demonstrates

**6.1. Complete data requiring an additional amount threshold check**

`Submit(DraftOrder(... Customer(... Address(...)), Money(...)))` both selects the `Submit` variant and checks the nested layers of data. When the shape matches and `orderId` has text, `when cents >= 10_000` classifies the order as needing review. The next normal branch applies to the case with the same shape and valid `orderId` but a smaller amount.

**6.2. Nested patterns can fail due to a null component**

`DraftOrder("O-102", Customer("C-9", null), Money(...))` does not match `Address(var city, var country)`. `DraftOrder("O-103", null, Money(...))` does not even match the nested `Customer(...)`. Both are handled by `case Submit(var draft)`.

**6.3. Fallbacks also handle invalid draft data**

`DraftOrder("  ", Customer(...), Money(...))` matches the structure but fails the `hasText(orderId)` guard, so it does not enter the first two branches. `Submit(null)` does not match the nested `DraftOrder(...)`, yet still matches `Submit(var draft)`. Both produce `"Incomplete submit"`.

**6.4. Type patterns and record patterns do not validate business rules**

`Cancel("O-100", "Customer requested")` enters the guarded branch; `Cancel("O-100", "  ")` has a whitespace-only reason, fails the guard, and reaches `"Invalid cancellation"`. These checks **do not verify that order O-100 actually exists or is allowed to be cancelled**.

**6.5. Constructor validation is distinct from matching**

`new Money("VND", -1)` and `new Address("", "VN")` are rejected by the compact constructors **before** any deconstruction happens. Record patterns are not responsible for blocking invalid domain data creation — invariants belong in the object construction contract or the DTO conversion step.

**6.6. Comparing `describe` with `describeExplicit`**

All six `Submit` inputs end with `equal=true`: the nested pattern results match the explicit accessor-based steps on the tested cases. This is **behavioral equivalence testing on a sample set**, not a proof that the two approaches are always equivalent when custom accessors have side effects or when logic changes.

**6.7. A `null` selector is not a null component**

`describe(null)` selects `case null` and returns `"Missing action"`. It differs from `describe(new Submit(null))`, which is treated as a `Submit` containing missing draft data.

**6.8. Exhaustiveness is preserved**

`OrderAction` is a sealed interface with only `Submit` and `Cancel` in this example; the switch has unguarded branches for each variant plus `case null`. Therefore, the `switch expression` does not need `default`. If `UpdateAddress` is later added to the hierarchy, recompiling requires reviewing the new case.

### This is an illustrative model, not a production order service

The `describe` method only **classifies and builds a descriptive string**. It does not save orders, charge money, deduct inventory, check ownership, check status, or emit events. The `10_000` threshold was chosen for readability, **not as a standard currency rule**. In a real system, decisions and side effects must live in an application service with a clear contract.

## 7. Reading nested patterns without mixing up component order

Record patterns use the **declaration order in the record**, not variable names, to bind components:

~~~java
record Address(String city, String country) {}
~~~

Given an `Address("Hue", "VN")`:

~~~java
// Java 21+ snippet, input has type Object.
if (input instanceof Address(var city, var country)) {
    System.out.println(city + "/" + country);
}
~~~

`city` receives `"Hue"`, and `country` receives `"VN"`. However:

~~~java
if (input instanceof Address(var country, var city)) {
    // SYNTACTICALLY VALID, but misleading variable names:
    // country actually receives "Hue"; city actually receives "VN".
}
~~~

This bug **is not necessarily caught by the compiler** because both components have the same type `String`. Therefore:

- Read the record signature before writing a pattern.
- Use local variable names that match the component meanings.
- Avoid deconstructing too many components of the same type when they are hard to distinguish visually.
- If misnaming carries high risk, **calling explicit accessors** such as `address.city()` and `address.country()` can be safer for maintainers.

**Do not treat a record pattern like a constructor call.** The syntax `Address(var city, var country)` in a `case` is a pattern that matches an existing value; it does not construct `new Address(...)`.

## 8. When does deep deconstruction become a problem?

The first branch in `describe` simultaneously reads the subtype, order draft, customer, address, money, and guard:

~~~java
// Snippet from the main example, body abbreviated.
case Submit(DraftOrder(var orderId,
        Customer(var customerId, Address(var city, var country)),
        Money(var currency, var cents)))
        when hasText(orderId) && cents >= 10_000 ->
        /* describe order needing review */;
~~~

This is useful when the goal is to **confirm that the entire structure is complete enough to proceed**. But as logic grows more complex, multi-level nested patterns can:

- Make component names hard to match against record declarations.
- Collapse multiple invalid reasons into a single “did not match”.
- Change error policy merely by reordering `case` branches.
- Repeat the same pattern structure across multiple branches with different guards.
- Couple code more tightly to the order and number of record components.
- Become harder to maintain when adding new fields or changing domain structure.
- Cause issues if custom accessors are impure or expensive.

### Split into named steps when specific error reasons are needed

The `describeExplicit` example uses:

~~~java
// Snippet inside a method returning String, with DraftOrder draft already available.
if (draft == null || !hasText(draft.orderId())) {
    return "Incomplete submit";
}
Customer customer = draft.customer();
Money total = draft.total();
if (customer == null || total == null) {
    return "Incomplete submit";
}
Address address = customer.deliveryAddress();
if (address == null) {
    return "Incomplete submit";
}
~~~

When business logic needs distinct error codes, each check path can return a `ValidationResult` or an enum such as `MISSING_CUSTOMER`, `MISSING_ADDRESS`, `INVALID_ORDER_ID` instead of every branch returning `"Incomplete"`.

**You do not have to switch everything to `if`.** You can combine them: use `switch` at the `OrderAction` level to select the command kind, then call `validateDraft(draft)` for multi-step business checks. Choose patterns where they express a clear structure, rather than forcing an entire workflow into a single `case`.

## 9. The `when` guard: classify, do not orchestrate side effects

In the example, the guards:

~~~java
when hasText(orderId) && cents >= 10_000
when hasText(orderId)
when hasText(id) && hasText(reason)
~~~

only read values and return a `boolean`. That is the right job for guards. The `hasText` helper is also pure, writing no data and calling no external service.

An anti-pattern would look like:

~~~java
// INTENTIONAL ILLUSTRATION OF BAD DESIGN, not standalone source.
case Submit(var draft) when paymentGateway.charge(draft) ->
        "Accepted";
~~~

If `charge` performs a transaction, the side effect can happen **during case selection**, even if it returns `false` and Java moves on to check later branches. `switch` does not automatically roll back transactions that already ran.

**A better approach:** deconstruct to extract data, validate, and produce a pure decision/value object; then in the application service perform persistence/charging/auditing with proper transactions, idempotency, and error handling.

### A long guard is not always more readable than a helper

When there are many conditions such as order state, permissions, limits, inventory, or data version, a chain like `when a && b && c && d` can obscure rejection reasons. Consider a `validate(...)` function that returns a structured result and can be tested independently. Avoid turning every business condition into a boolean `case`.

## 10. Dominance and case ordering in the domain

Classify from **specific cases to general cases**:

~~~java
// Java 21+, snippet inside a switch on OrderAction.
case Submit(DraftOrder(var id, var customer, var total))
        when hasText(id) -> "Ready";
case Submit(var draft) -> "Incomplete";
~~~

If `case Submit(var draft)` is placed first, it covers every `Submit`, so the more specific branch after it is **dominated** under Java's dominance rules. The compiler helps detect several forms of shadowed branches.

Similarly, in the main program:

1. `Submit(... nested ...) when cents >= 10_000` first.
2. `Submit(... nested ...) when hasText(orderId)` second.
3. Unguarded `Submit(var draft)` at the end of the `Submit` group.

The condition in the first branch also needs `hasText(orderId)` to avoid classifying a draft with an empty order ID as needing review. **The compiler does not prove arbitrary complex boolean relationships between guards**; classification order and boundary values still must be tested.

### What role does the unguarded branch play?

The `case Submit(var draft)` branch catches `Submit` values that did not satisfy earlier branches: missing draft, missing customer, missing address, missing money, or invalid orderId. It makes classification type-exhaustive, though it does not explain in detail **why** the input was invalid.

Choose a general fallback only when the contract does not require distinguishing individual reasons; otherwise, use a validation result or more meaningful branches.

## 11. Exhaustiveness helps the domain model evolve under control

A closed sealed hierarchy lets the compiler know the list of permitted direct subtypes. With:

~~~java
sealed interface OrderAction permits Submit, Cancel {}
record Submit(DraftOrder draft) implements OrderAction {}
record Cancel(String orderId, String reason) implements OrderAction {}
~~~

a `switch expression` with complete branches handling `Submit` and `Cancel` does not need `default`. When `RescheduleDelivery` is added, code that switches on `OrderAction` must be revisited.

~~~java
// CHANGE ILLUSTRATION, not a standalone runnable file.
sealed interface OrderAction
        permits Submit, Cancel, RescheduleDelivery {}

record RescheduleDelivery(String orderId, Address address)
        implements OrderAction {}
~~~

**Strength:** exhaustive `switch expression`s without the new branch produce compile-time errors on recompilation, reminding the author to decide how to handle the new action. An overly broad `default -> "Other"` suppresses that signal.

**Limitation:** if a module has a `non-sealed` branch, the subtype set can be open and exhaustiveness guarantees change with the design. Do not assume that every interface marked `sealed` automatically guarantees that no concrete branch ever needs a fallback in every extensible structure.

### `null` is not a permitted subtype

`null` does not represent a variant in the `permits` list. In the demo, `case null` is an explicit policy that accepts `null` and returns `"Missing action"`. Another option is `Objects.requireNonNull(action)` to reject null before the `switch`. What matters is **choosing a clear policy**.

## 12. Deconstruction and API evolution

Record patterns depend on the **record shape at compile time**. Consider:

~~~java
record Address(String city, String country) {}
~~~

and the pattern:

~~~java
case Address(var city, var country) -> ...
~~~

If `Address` later changes to:

~~~java
// ILLUSTRATION of a new schema version, not declared alongside the old one.
record Address(String city, String region, String country) {}
~~~

the two-component record pattern no longer matches the arity; every site using the pattern must be updated and recompiled. This is **intentional coupling to data shape**.

Compare:

- **Deconstruction:** expresses structure clearly and is very concise when multiple components are needed together, but is affected when component count or order changes.
- **Named accessors:** `address.city()` can remain valid when a record adds another component as long as the existing accessor is preserved.
- **Domain methods:** `order.isDeliverable()` expresses a policy; its implementation can change without callers knowing all internal data.

**Changing record components also affects constructors, serialization, and API compatibility**, not just patterns. Never “swap” two components of the same type without considering the consequences, as the compiler may not detect swapped meanings.

### Be especially careful at module/public API boundaries

Within an internal module, changing a record shape and updating all patterns can be a controlled refactoring step. For public APIs or persisted message schemas, changing shape can break compiled clients, serializers, deserializers, and historical data.

A resilient design typically has:
- External DTOs/schemas with explicit versioning.
- A conversion layer from DTOs to validated domain records.
- Domain operations using meaningful methods instead of depending on every component unnecessarily.
- Deconstruction used where shape matching is genuinely needed and you own both the pattern sites and the domain model.

## 13. Are record patterns just a form of getter calls?

Each record component has a corresponding accessor, and **record patterns invoke those accessors** to extract values. For ordinary records with simple accessors, this is straightforward and the JVM can optimize it. However, Java allows **custom accessors**:

~~~java
// Java snippet: illustrating custom accessor capability.
record Counter(int value) {
    public int value() {
        System.out.println("accessor invoked");
        return value;
    }
}
~~~

This is valid code, but you **should not** put business side effects inside accessors of a domain value object. Nested matching may access components while testing a pattern before moving on to a fallback case; never write business logic that depends on an accessor “definitely running only once”.

Likewise, a custom accessor can throw an exception; throwing is not equivalent to a pattern failing to match and falling through to the next case. If you need network/database access or stateful computation, call an explicit service/method **outside the pattern** and handle errors explicitly.

### How immutable are records?

Record components are fields that cannot be reassigned after construction (outside abnormal language mechanisms), but **they do not automatically make referenced objects deeply immutable**.

~~~java
// Snippet meaningful when the list must be protected.
record LineItems(java.util.List<String> skuIds) {
    LineItems {
        skuIds = java.util.List.copyOf(skuIds);
    }
}
~~~

`List.copyOf` creates an unmodifiable list per the API contract and rejects `null`; however, if the elements themselves are mutable objects, additional strategies are needed when true deep immutability is required. In the main demo, `Address` and `Money` only use `String` and primitive types, keeping the model simpler.

## 14. Choosing record patterns or accessors by business intent

### Use record patterns when

- You need to branch clearly across variants of a sealed domain hierarchy.
- The structure is small or medium-sized and the data is genuinely a value-like record.
- You want to check a nested shape such as “must have complete `Customer → Address`”.
- You need multiple components of the same record to produce a short result.
- You want the compiler to help catch missing variants in an exhaustive `switch`.
- Your codebase maintains both the record declaration and the deconstruction sites.

### Use accessors or domain methods when

- Only one field is needed: `order.id()` is usually clearer than deconstructing all of `Order`.
- Data is in draft form and needs **specific error reasons** for each missing component.
- Nested patterns repeat across many levels with too many `var`s of the same type.
- The domain model is likely to add fields or reorder components frequently.
- You want to hide internal structure and keep a public API stable.
- There is rich behavior like `order.canBeCancelledBy(user)` that should not be duplicated across `when` clauses.
- Custom accessors or side effects exist and you want explicit control over when reads occur.

### A hybrid option that often works well

~~~java
// ARCHITECTURE ILLUSTRATION, not standalone runnable source.
return switch (action) {
    case Submit(var draft) -> submitService.validateAndProcess(draft);
    case Cancel(var id, var reason) -> cancelService.process(id, reason);
    case null -> handleMissingAction();
};
~~~

Here `switch` selects the **action variant** without carrying the entire validation or workflow. If you need to deconstruct `Address` in a pure formatting function, you can still use a record pattern there. **There is no rule that choosing pattern matching means decomposing every object down to its smallest components.**

## 15. Performance: do not choose a design by line count alone

A nested pattern does not create a new copy of the record at each level. It performs matching and component access; the JIT can inline simple accessors and optimize observable code.

However:
- A branch whose nested match fails may lead to **trying another pattern**.
- Guards run **after** the record pattern part of the `case` has matched.
- Custom accessors can be expensive, re-read, or have side effects.
- String concatenation, validation, I/O, or business computation often dominates deconstruction time.
- Shorter code does not mean faster bytecode or machine execution.

**The `describe` and `describeExplicit` examples only verify results, not speed**. To draw performance conclusions, use **JMH**, build inputs outside the measured section, use warmup/forks/measurements, verify equivalence, and test multiple data shapes; inspect a profiler to identify actual hot paths.

**Recommendation:** choose for clarity and contract correctness first. Only replace nested patterns with manual accessors for performance if you have measured a meaningful difference in a real workload.

## 16. Common mistakes when deconstructing domain records

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Naming variables out of order for same-type components | Compiler may not catch it; data is misinterpreted | Check the record declaration; use accurate names or named accessors |
| Assuming `Customer(var id, Address(...))` matches a null address | Nested branch fails to match and falls through | Distinguish nested type/record patterns from `var address` |
| Assuming records automatically validate all invariants | `DraftOrder(null, null, null)` can still be created | Enforce invariants in constructors/factories/validation per contract |
| Deeply deconstructing everywhere | Coupling to record shape; hard to tell where data is missing | Separate validation and use domain methods where appropriate |
| Having no fallback for draft data | Incomplete structures are not handled as intended | Add a general branch or a validation result |
| Placing a general case before a guarded case | Guarded case is shadowed or compiler reports dominance | Place specific cases first |
| Adding `default` to a sealed `switch` | Hides missing cases when new variants are added | Keep exhaustive cases when the variant set is closed |
| Calling services with side effects in `when` | Can trigger actions before a branch is chosen | Keep guards pure; run workflows in services |
| Using deconstruction as value comparison like `equals` | Misunderstands the purpose of patterns | Use `equals` for value equality; patterns for type/shape checks |
| Creating domain events before business action occurs | Confuses commands with events | Name requests and events distinctly |
| Reordering record components without updating clients | Patterns may bind wrong meanings; public APIs break | Review contracts/schemas, run tests, and version APIs |
| Treating accessor counts in a demo as a benchmark | Does not measure real runtime/JIT behavior | Use JMH/profilers with representative inputs |
| Using generic record patterns without understanding type inference | Can misread type inference and type erasure | Check static types, constrain patterns appropriately, and compile tests |

## 17. Essential test suite for the record case study

| Input / condition | Expected result | Rule verified |
| --- | --- | --- |
| `Submit(DraftOrder("O-100", Customer(...Address...), Money("VND",12500)))` | `Review ...` | Nested pattern matches; threshold guard works |
| Complete order totaling 500 cents | `Ready ...` | Review branch skipped; normal branch selected |
| `Customer.deliveryAddress == null` | `Incomplete submit` | Nested `Address(...)` does not match |
| `DraftOrder.customer == null` | `Incomplete submit` | Nested `Customer(...)` does not match |
| `DraftOrder.orderId` all whitespace | `Incomplete submit` | Guard rejects invalid data |
| `Submit(null)` | `Incomplete submit` | `Submit(var draft)` still matches |
| `Cancel` with non-blank reason | `Cancel ...` | Guarded branch matches |
| `Cancel` with blank reason | `Invalid cancellation` | Fallback branch for same subtype |
| `null` selector | `Missing action` | Explicit `case null` |
| `new Money("VND",-1)` | `IllegalArgumentException` | Constructor invariant |
| `new Address("", "VN")` | `IllegalArgumentException` | Constructor invariant |
| Adding a new subtype without adding a case | Compile error on exhaustiveness | Compiler assists when domain expands |
| Changing component count of `DraftOrder` | Old pattern needs updating/recompiling | Record shape is a contract |

In the sample program, the `equal=true` suffix on the first six lines verifies that **both implementations return the same result** for the chosen inputs. In a real project, add property-based tests or unit tests for many valid/invalid combinations, especially when imported data has many edge cases.

### Compile-time tests and runtime tests have different jobs

- **Compile-time:** catches wrong component arity in patterns, dominance, out-of-scope variables, or non-exhaustive `switch expression`s.
- **Runtime:** catches missing data, failed business validation, invalid currencies, branch priority logic, and transactional effects.
- **Integration:** verifies DTOs/schemas, deserialization, persistence, idempotency, authorization, and version compatibility.

You cannot replace all business testing with the compiler; nor should you write a runtime test to “prove” a compile-time error by bypassing compilation.

## 18. Practice exercises

### Exercise 1 — Reading a nested record pattern

Given:

~~~java
record Contact(String email) {}
record Member(String id, Contact contact) {}
~~~

For `Object input`, predict the behavior:

~~~java
String result = switch (input) {
    case Member(var id, Contact(var email)) ->
            id + ":" + email;
    case Member(var id, var contact) -> "Missing contact";
    case null -> "No member";
    default -> "Other";
};
~~~

**Answer:** `new Member("M1", new Contact("m@example.com"))` takes the first branch; `new Member("M2", null)` takes `"Missing contact"`; a null selector takes `"No member"`. The nested `Contact(...)` does not match a null component; `var contact` can bind null.

### Exercise 2 — Finding a component naming mistake

Given `record Money(String currency, long cents) {}`:

~~~java
// INTENTIONALLY WRONG VARIABLE SEMANTICS, even though Java can compile it.
if (input instanceof Money(var cents, var currency)) {
    System.out.println(cents + " " + currency);
}
~~~

**Answer:** The first component is `currency`, and the second is `cents`. The names in the pattern are swapped, so `cents` actually has type `String` and `currency` has type `long`. Fix it to `Money(var currency, var cents)`. This illustrates why you must check patterns against the record declaration rather than guessing from chosen names.

### Exercise 3 — Choosing where to place invariants

A system only allows `ConfirmedOrder` to have a non-empty `orderId` and a non-null `total`. Should you write `when orderId != null && !orderId.isBlank() && total != null` in every `switch`, or validate in the constructor/factory?

**Suggested answer:** Core invariants belong in the **constructor/factory** so an object cannot be constructed through valid paths with violating data. Deconstruction in operations can then rely on those invariants. At the boundary, you must still catch errors and return appropriate results for invalid input.

### Exercise 4 — Choosing a deep pattern or a helper

A function needs to report `MISSING_CUSTOMER`, `MISSING_ADDRESS`, and `MISSING_TOTAL` separately. Should it just use a single `case Submit(DraftOrder(... Customer(... Address(...)), Money(...)))` with a fallback `"Incomplete"`?

**Suggested answer:** Not sufficient if distinct error messages are required. Use a `validateDraft` helper returning a validation code or check accessors step by step explicitly. You can keep `switch` to select `Submit`/`Cancel`, while placing multi-reason checks in a named helper.

### Exercise 5 — Adding a new action

Add `record UpdateAddress(String orderId, Address address) implements OrderAction {}` to the sealed hierarchy. What needs to be done?

**Answer:** Update `permits` and add an appropriate `case` for `UpdateAddress` in exhaustive `switch expression`s handling `OrderAction`. The compiler can help locate missing branches. You also need to test null/validation handling and update APIs/schemas if the action can arrive from external systems.

### Exercise 6 — Does deconstruction copy the original object?

With `Customer(var id, var address)`, is `address` a deep copy of `Address`?

**Answer:** No. The pattern binds component values. It does not automatically copy the record or deep-copy the object graph. Records generally have final fields at the component level, but if a component references a mutable object, separate immutability measures are needed.

### Exercise 7 — Shadowed guard

~~~java
// INTENTIONALLY WRONG: assume input has type Object and DraftOrder is valid.
String value = switch (input) {
    case DraftOrder(var id, var customer, var total) -> "draft";
    case DraftOrder(var id, var customer, var total)
            when hasText(id) -> "valid id";
    case null -> "null";
    default -> "other";
};
~~~

**Answer:** The first unguarded case covers all `DraftOrder` values, so the `when hasText(id)` case after it is dominated. Put the guarded case first and the general case after it.

## 19. Decision checklist for the domain

Before putting record deconstruction into production, check:

1. **Are domain types clearly named?** `DraftOrder` is different from `ConfirmedOrder`; `Submit` is a command, not an event.
2. **Is the record shape stable?** Patterns depend on component order, count, and types.
3. **Are all components actually needed?** If only one field is needed, a named accessor may be clearer.
4. **Are nested null semantics right?** A null selector, a null component, and an empty string are different cases.
5. **Are invariants enforced at the right boundary?** Constructors/factories for domain types, validation for DTOs.
6. **Are guards pure?** Do not call payment gateways, write repositories, or critical auditing just to pick a branch.
7. **Are cases ordered from specific to general?** Avoid dominance and wrong classification priority.
8. **Is a sealed `switch` exhaustive?** Avoid unnecessary `default` branches that hide newly added subtypes.
9. **Are detailed error reasons needed?** If so, a validation result is usually better than one nested pattern with a generic fallback.
10. **Can public API code tolerate record shape changes?** Consider accessors/domain methods and compatibility.
11. **Have you tested on the target JDK?** Record patterns and pattern `switch` are final as of Java 21.
12. **Have you tested both compile time and runtime?** Run complete inputs, missing inputs, true/false guards, nulls, and invalid invariants.
13. **Are side effects hidden in accessors?** Pattern matching is not the place to control I/O or transactions.
14. **Do you have benchmarks if decisions are performance-driven?** Do not infer cost from the number of parentheses in a nested pattern.

## 20. Summary

**Deconstruction is a tool for inspecting data structure, not a reason to expose every domain detail.**

- `record` helps represent values with clear components.
- **Record patterns** check a record and bind components; **nested record patterns** additionally check nested structure.
- `sealed` combined with `switch expression` handles a controlled set of variants and gives compiler signals when subtypes are added.
- **`when`** classifies using pure conditions and should not perform transactions or side effects.
- **Draft data** needs fallbacks/validation because components may be missing; **validated domain types** should be protected by invariants in constructors/factories.
- Keep **named accessors** and **domain methods** where they express intent better than nested deconstruction, especially when API stability matters.
- Test non-matching cases, null components, false guards, added subtypes, and record shape changes.
- Do not choose nested patterns just because you can write a very short expression. Choose the approach that makes it easy for readers to see **which data is accepted, which cases are rejected, and who is responsible for business invariants**.

**Official sources:** [JEP 395 — Records](https://openjdk.org/jeps/395); [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409); [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
