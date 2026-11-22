# Modeling Variants with Subtypes in Domain Models (Java 21+)

## 1. What Is a Variant and Why Use Subtypes?

In domain model design, an entity or concept often has **multiple valid variants** with their own data and rules. For example, an order can be delivered in three ways:

- **Store pickup**: requires `storeId`.
- **Home delivery**: requires an address and an express delivery option.
- **Parcel locker**: requires `lockerId`.

A common design is to lump all fields into a single record:

~~~java
enum DeliveryKind { PICKUP, HOME, LOCKER }

record DeliveryData(
        DeliveryKind kind,
        String storeId,
        String lockerId,
        String city,
        String street,
        boolean express) {}
~~~

This is an **illustrative snippet**, not a recommended model. It allows nonsensical combinations:

- `kind == PICKUP` but without `storeId`.
- `kind == HOME` but `city == null`, or also having `lockerId`.
- `kind == LOCKER` but with `express` enabled, a flag that only makes sense for home delivery.

The application has to use chains of `if` statements to validate every valid field combination. If one branch misses a check, the object can still be created in an invalid state. This is a sign that **the data model does not accurately represent the variants**.

A better approach is for **each variant to have its own subtype**: carrying only the fields it needs and taking responsibility for validating its own constraints.

> Rule of thumb: When variants have **different data structures**, consider modeling a sum type using a set of subtypes; when they only differ by state name, an `enum` may be simpler.

## 2. Choosing a "Closed Set of Variants" with `sealed interface`

With Java 17+, a `sealed interface` directly specifies the types permitted to implement it:

~~~java
sealed interface DeliveryOption
        permits StorePickup, HomeDelivery, ParcelLocker {}

record StorePickup(String storeId) implements DeliveryOption {}
record HomeDelivery(Address destination, boolean express)
        implements DeliveryOption {}
record ParcelLocker(String lockerId) implements DeliveryOption {}

record Address(String city, String street) {}
~~~

These are **illustrative declarations**; below we will add validation to the constructors and put everything into a complete program.

Model semantics:

| Subtype | Specific Data | Business Meaning |
| --- | --- | --- |
| `StorePickup` | `storeId` | Customer picks up at the store |
| `HomeDelivery` | `Address destination`, `express` | Delivered to the address specified by the customer |
| `ParcelLocker` | `lockerId` | Delivered to a parcel locker |
| `DeliveryOption` | Declares no redundant field combinations | Common abstraction for the variants |

`DeliveryOption` represents the concept of "delivery method", **not** an object to be instantiated directly. The three subtypes carry three different data shapes.

**Why use `sealed`?** With a controlled set of business variants in the codebase, `permits` restricts **the direct subtypes**. `record` types are `final` by default, so there cannot be arbitrary subclasses of `StorePickup`, `HomeDelivery`, or `ParcelLocker`.

A direct subclass of a `sealed` type must, in principle, choose one of `final`, `sealed`, or `non-sealed`; in this example, `record` already satisfies this by being `final`. If `non-sealed` is used on a branch, deeper subtypes can be extended; the "closedness" of the entire hierarchy will differ. Do not confuse `sealed` with automatically forbidding all invalid data states: **constructor validation is still necessary**.

## 3. Protecting Invariants at Variant Creation Time

An *invariant* is a condition that must hold true for every valid object in the domain. For example:

- `StorePickup.storeId` must be non-`null` and non-blank.
- `ParcelLocker.lockerId` must be non-`null` and non-blank.
- `HomeDelivery.destination` must be non-`null`.
- `Address.city` and `Address.street` must be non-`null` and non-blank.

With `record`, we can use a **compact constructor** for validation:

~~~java
static String requireText(String text, String field) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(field);
    }
    return text;
}

record Address(String city, String street) {
    Address {
        requireText(city, "city");
        requireText(street, "street");
    }
}

record StorePickup(String storeId) implements DeliveryOption {
    StorePickup {
        requireText(storeId, "storeId");
    }
}

record HomeDelivery(Address destination, boolean express)
        implements DeliveryOption {
    HomeDelivery {
        if (destination == null) {
            throw new IllegalArgumentException("destination");
        }
    }
}

record ParcelLocker(String lockerId) implements DeliveryOption {
    ParcelLocker {
        requireText(lockerId, "lockerId");
    }
}
~~~

This is an **illustrative snippet of components** used within the same class; the `requireText` method and `DeliveryOption` interface need to be in the enclosing scope. The complete program in section 7 arranges them in full.

With a compact constructor, Java automatically assigns the parameters to the record components after the constructor body. If a condition fails, it throws `IllegalArgumentException` immediately at object creation; there is no need for numerous business methods to re-check improperly constructed objects.

For example:

~~~java
new StorePickup("S1");                     // Valid
new HomeDelivery(new Address("Ha Noi", "12 Pho Hue"), true); // Valid

new StorePickup(" ");                      // IllegalArgumentException
new HomeDelivery(null, true);              // IllegalArgumentException
~~~

**Note on immutability:** records generate `private final` components and accessors, but only guarantee *shallow immutability*. If a component holds a `List` or a mutable object, you must create a defensive copy or use an immutable value object when the domain requires it. In this example, the components are `String`, `boolean`, and a valid `Address` record, so there are no mutable collections to handle.

## 4. Pattern Matching Turns Subtype Sets into Clear Branches

Once the model has concrete subtypes, we can write a `switch` expression over `DeliveryOption`:

~~~java
static int fee(DeliveryOption option) {
    java.util.Objects.requireNonNull(option, "option");

    return switch (option) {
        case StorePickup(var storeId) -> 0;
        case ParcelLocker(var lockerId) -> 15;
        case HomeDelivery(var destination, var express)
                when express -> 50;
        case HomeDelivery(var destination, var express) -> 25;
    };
}
~~~

The numbers `0`, `15`, `50`, and `25` are only **illustrative fee rules**, not an actual rate table.

Notable points:

1. `StorePickup(...)` and `ParcelLocker(...)` are **record patterns**, deconstructing the corresponding components of each subtype.
2. `HomeDelivery(var destination, var express) when express` is a **guarded pattern**: it only applies the express fee if the `express` component is `true`.
3. The next `HomeDelivery(...)` branch handles home delivery cases that do not satisfy the guard. Place the specific branch with `when` **before** the general `HomeDelivery` branch.
4. The `switch` covers all three permitted subtypes of the `sealed interface`. Therefore, **no `default` is needed** in this example.
5. `Objects.requireNonNull` makes the input contract explicit: `null` is not accepted. If `null` is passed, the program throws `NullPointerException` at this check, rather than treating `null` as a delivery variant.

**Benefit when adding a variant:** Suppose `DroneDelivery` is later added to the `permits` list. When recompiling the code, a `switch` expression without `default` that does not yet handle the new subtype will be reported by the compiler as **not exhaustive**. This is a key benefit of modeling a closed set of variants.

This does **not** mean all logic in the system is automatically fixed; places with a broad `default`, logic using `if`, or systems running with classes compiled at different times still need to be checked. The benefit is having an additional guarantee and error reporting **at compile time**.

## 5. Nested Record Patterns: Extracting Specific Data Without Casting

For home delivery, the address is modeled with the `Address` record. Java 21 allows deconstructing across two levels:

~~~java
static String route(DeliveryOption option) {
    java.util.Objects.requireNonNull(option, "option");

    return switch (option) {
        case StorePickup(var storeId) -> "store:" + storeId;
        case ParcelLocker(var lockerId) -> "locker:" + lockerId;
        case HomeDelivery(Address(var city, var street), var express) ->
                "home:" + city + "/" + street
                        + (express ? ":express" : ":standard");
    };
}
~~~

This is an illustrative method using the defined subtypes; the full code is presented in section 7.

- `HomeDelivery(...)` matches the home delivery variant.
- `Address(var city, var street)` deconstructs the record inside the `destination` component.
- `city` and `street` are inner pattern variables; `express` is an outer pattern variable of `HomeDelivery`.
- There is no need for chained calls like `((HomeDelivery) option).destination().city()` or manual casting.
- The variables are only in scope within the `case` branch where the pattern matched.

A nested `Address(...)` pattern requires the `destination` component to have the matching shape. Because the `HomeDelivery` constructor forbids `destination == null`, we do not expect a valid object to have a `null` address. Even so, this is a guarantee from the **domain invariant**, not because the compiler automatically infers that all data is always business-valid.

**Be careful with `null` in record components:** component patterns using `var` can match a `null` value. A nested record pattern also does not replace domain input validation. Here `Address` actively forbids blank or null `city` and `street`, so the `route` method can rely on that invariant.

### Comparison with Manual Type Checks

~~~java
static String routeOldStyle(DeliveryOption option) {
    if (option instanceof StorePickup pickup) {
        return "store:" + pickup.storeId();
    }
    if (option instanceof ParcelLocker locker) {
        return "locker:" + locker.lockerId();
    }
    if (option instanceof HomeDelivery home) {
        Address address = home.destination();
        return "home:" + address.city() + "/" + address.street()
                + (home.express() ? ":express" : ":standard");
    }
    throw new IllegalStateException("Unsupported delivery option");
}
~~~

The `if/else` approach using type patterns above is still valid and sometimes easier to read. However, with a closed `sealed` set and a transformation into **a single result value**, a `switch` expression usually expresses handling all variants more clearly and enables the compiler to check exhaustiveness.

## 6. Variants Differ from States and "Option Flags"

Not every `enum` value requires creating a new subtype. You should identify the **essential difference**:

- **Variant subtype:** different data and/or structural rules. For example, `StorePickup(storeId)` differs from `HomeDelivery(address, express)`.
- **State within the same variant:** an order has `status = CREATED/PAID/CANCELLED`, but all states share the same data. An `enum` can be used if there is no need to represent different data sets across states.
- **Variant-internal option:** `express` only makes sense within `HomeDelivery`, so place it inside that subtype, not on the common interface for all delivery methods.

Two questions help guide the choice:

1. **Are there field combinations that cannot be valid?** If yes, subtypes usually help eliminate unrelated fields from each variant.
2. **Do the variants have different required fields?** If they differ significantly, subtypes let constructors enforce the exact required data.

If all variants are just a label in a column, with no specific data or structural changes, an `enum` may suffice. If variants have rich behavior, also consider placing **behavior** close to the corresponding subtype instead of creating one giant `switch` scattered across every layer of the application.

## 7. Complete Java 21 Program

Save the following code as **`DeliveryVariantsDemo.java`**. The example validates constructors, calculates fees, builds routes, deconstructs nested records, and runs test cases without any external libraries outside the JDK.

~~~java
public class DeliveryVariantsDemo {
    sealed interface DeliveryOption
            permits StorePickup, HomeDelivery, ParcelLocker {}

    record Address(String city, String street) {
        Address {
            requireText(city, "city");
            requireText(street, "street");
        }
    }

    record StorePickup(String storeId) implements DeliveryOption {
        StorePickup {
            requireText(storeId, "storeId");
        }
    }

    record HomeDelivery(Address destination, boolean express)
            implements DeliveryOption {
        HomeDelivery {
            if (destination == null) {
                throw new IllegalArgumentException("destination");
            }
        }
    }

    record ParcelLocker(String lockerId) implements DeliveryOption {
        ParcelLocker {
            requireText(lockerId, "lockerId");
        }
    }

    static String requireText(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(field);
        }
        return text;
    }

    static int fee(DeliveryOption option) {
        java.util.Objects.requireNonNull(option, "option");
        return switch (option) {
            case StorePickup(var storeId) -> 0;
            case ParcelLocker(var lockerId) -> 15;
            case HomeDelivery(var destination, var express)
                    when express -> 50;
            case HomeDelivery(var destination, var express) -> 25;
        };
    }

    static String route(DeliveryOption option) {
        java.util.Objects.requireNonNull(option, "option");
        return switch (option) {
            case StorePickup(var storeId) -> "store:" + storeId;
            case ParcelLocker(var lockerId) -> "locker:" + lockerId;
            case HomeDelivery(Address(var city, var street), var express) ->
                "home:" + city + "/" + street
                    + (express ? ":express" : ":standard");
        };
    }

    private static int passed = 0;

    static void check(boolean ok, String name) {
        if (!ok) {
            throw new AssertionError(name);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    static void expectInvalid(Runnable action, String name) {
        try {
            action.run();
            throw new AssertionError(
                    "Expected IllegalArgumentException: " + name);
        } catch (IllegalArgumentException expected) {
            check(true, name);
        }
    }

    public static void main(String[] args) {
        DeliveryOption pickup = new StorePickup("S1");
        Address address = new Address("Ha Noi", "12 Pho Hue");
        DeliveryOption standard = new HomeDelivery(address, false);
        DeliveryOption express = new HomeDelivery(address, true);
        DeliveryOption locker = new ParcelLocker("L9");

        check(fee(pickup) == 0, "pickup fee");
        check(route(pickup).equals("store:S1"), "pickup route");
        check(fee(standard) == 25, "standard fee");
        check(fee(express) == 50, "express fee");
        check(route(express).equals("home:Ha Noi/12 Pho Hue:express"),
                "express route");
        check(fee(locker) == 15, "locker fee");
        check(route(locker).equals("locker:L9"), "locker route");

        Object unknown = express;
        check(unknown instanceof HomeDelivery(
                Address(var city, var street), var fast)
                && city.equals("Ha Noi") && fast,
                "nested pattern");

        check(pickup.equals(new StorePickup("S1")),
                "record value equality");

        expectInvalid(() -> new StorePickup(" "), "blank store id");
        expectInvalid(() -> new Address("", "12 Pho Hue"), "blank city");
        expectInvalid(() -> new HomeDelivery(null, true),
                "null destination");
        expectInvalid(() -> new ParcelLocker(""), "blank locker id");

        try {
            fee(null);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            check(true, "null selector");
        }

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac --release 21 DeliveryVariantsDemo.java
java DeliveryVariantsDemo
~~~

**Expected output:**

~~~text
PASS pickup fee
PASS pickup route
PASS standard fee
PASS express fee
PASS express route
PASS locker fee
PASS locker route
PASS nested pattern
PASS record value equality
PASS blank store id
PASS blank city
PASS null destination
PASS blank locker id
PASS null selector
ALL PASSED: 14
~~~

### Reading the Test Results

- The `pickup`, `standard`, `express`, and `locker` cases verify that **each subtype** has its fee and route according to the example rules.
- `nested pattern` verifies that the pattern `HomeDelivery(Address(var city, var street), var fast)` properly deconstructs the subtype and nested record from an input variable with static type `Object`.
- `record value equality` verifies that two `StorePickup("S1")` records with equal component values return `true` for `equals`. This is the value-equality semantics generated by records.
- The four `expectInvalid` cases verify that valid objects cannot be created with blank store/locker IDs, blank city, or a null address.
- `null selector` verifies that `fee` does not accept a "null variant". This is a specific API choice: throwing `NullPointerException` via `Objects.requireNonNull`.
- Each check uses `AssertionError` to fail fast without depending on the `-ea` flag of `java`. Thus, `ALL PASSED: 14` is only printed when all tests pass.

## 8. Adding a New Variant Without Missing Handlers

Suppose the domain adds drone delivery with its own specific data `landingZone`. From a design standpoint, we will:

1. Create the subtype `DroneDelivery(String landingZone)` with corresponding constructor validation.
2. Add that subtype to `DeliveryOption`'s `permits` clause.
3. Recompile and review `switch` expressions without `default`: places that do not yet handle `DroneDelivery` will need a new branch.
4. Add tests for fees, routes, invalid data, and related integrations.

Example of the new subtype (illustrative, **not** included in the program in section 7):

~~~java
record DroneDelivery(String landingZone) implements DeliveryOption {
    DroneDelivery {
        requireText(landingZone, "landingZone");
    }
}
~~~

This is not "free extensibility". If the number of variants changes frequently due to external plugins, closing the list with `sealed` may be an unsuitable restriction. In that case, consider an open interface with a dedicated behavioral contract or an on-demand handler registration mechanism.

**Do not add `default -> ...` to every `switch` just to avoid errors when adding a subtype.** An overly broad default branch can mask forgetting to update handling for an important variant. With a closed set of variants, leveraging exhaustiveness checking is usually more helpful.

## 9. When to Use Subtypes, Enums, or Polymorphism?

| Option | Strengths | Limitations / Considerations |
| --- | --- | --- |
| `enum` | Simple, suitable for state labels or choices without variant-specific data | Cannot natively represent different field structures per variant |
| `sealed interface` + `record` | Closed set of variants, each subtype has its own payload, supports pattern matching and exhaustiveness checking | Adding a subtype requires updating handlers; records are best suited for value-like data |
| `sealed abstract class` + subclasses | Can share common state/mechanisms or manage complex hierarchies | Requires controlling inheritance, constructors, and mutability |
| Regular interface + implementations | Suitable for systems that allow external plugins/modules to extend | Compiler lacks a closed subtype list to provide similar exhaustiveness guarantees |
| Polymorphism via methods on subtypes | Keeps behavior close to data, avoiding many scattered switches | Needs consideration if there are many independent transformations that change frequently |

For a **domain entity with identity**, lifecycle, and mutable state, do not rush to use `record` just for its concise syntax. Records fit immutable **value-like variants** and data passed across layers. If a subtype must protect controlled state-mutating behavior, a class with explicit constructors, methods, and encapsulation may be a better choice.

## 10. Common Modeling Mistakes

**Mistake 1 — Using one "all-fields" object and leaving most fields null.** This introduces many invalid states into the model. Create subtypes for variants with different required data.

**Mistake 2 — Thinking `sealed` replaces validation.** `sealed` only restricts direct subtypes; it does not prove that `storeId` is valid or `Address` is complete. Protect invariants at initialization.

**Mistake 3 — Placing a variant-specific flag on the common interface.** The `express` flag belongs only to home delivery. If every delivery type has it, nonsensical combinations will appear.

**Mistake 4 — Using `default` to hide missed variant handling.** An exhaustive `switch` expression on a closed subtype set provides compiler-checked safety. Do not discard that benefit thoughtlessly.

**Mistake 5 — Ignoring a `null` selector.** `null` does not automatically become a subtype of an interface. Decide the contract clearly: reject early with `requireNonNull`, handle with `case null` if the business logic allows it, or validate inputs at the system boundary.

**Mistake 6 — Mistaking records for deeply immutable.** Records create `final` fields, but components can still reference mutable objects. If the domain demands deeper immutability, design for it proactively.

**Mistake 7 — Overusing one giant `switch` for all business logic.** If behaviors truly belong to each subtype, consider polymorphism. Use pattern matching when you need to **classify, transform, integrate, or present** variants into a clear result.

**Mistake 8 — Treating every peer value as a subtype.** For example, a status with 3 priority levels but no distinct data; creating three classes just to replace an enum can make the model needlessly bloated.

## 11. Checklist for Real-World Projects

Before implementing variants with subtypes, ask yourself:

1. Have all **valid variants** in the current domain scope been fully listed?
2. Does each variant have only its own **required fields**, without carrying fields used only by other variants?
3. Do constructors/factories check invariants such as null, blank text, value bounds, and cross-field relationships?
4. Is a **closed** set of variants needed? If so, does `sealed` fit extensibility and module encapsulation needs?
5. Is every `switch` handling the variants exhaustive? Is there a `default` branch accidentally masking a new subtype?
6. Is `null` handling clearly defined at system boundaries?
7. Are there tests for **each subtype**, valid data, invalid data, and edge cases?
8. Do payloads contain mutable objects? Is defensive copying needed to preserve invariants over time?
9. Should business rules live on the subtypes or be handled centrally via pattern matching?
10. When adding a new variant, do review and testing processes ensure all relevant places are updated?

### Extension Exercises

- Add a `CurbsidePickup(String storeId, String parkingSpot)` subtype: both strings must be non-blank. Update `permits`, `fee`, `route`, and tests.
- Change `HomeDelivery` to include `deliveryWindow`, and add validation disallowing a blank delivery window. Check how places using record patterns need to update their structure.
- Try removing the `ParcelLocker` branch from a `switch` expression without `default` and observe the compiler exhaustiveness error.
- Write a handler of type `DeliveryOption -> String` returning a display message, then decide whether that logic belongs in a centralized `switch` or in a polymorphic method.

**Key takeaway:** Modeling variants with subtypes is a way to encode **structural differences and invariants** into Java's type system. A `sealed interface` defines a controlled set of variants; `record` holds immutable value-like payloads; constructors protect valid states; and pattern matching in `switch`/record patterns handles each case clearly, with exhaustiveness checking support when appropriate.
