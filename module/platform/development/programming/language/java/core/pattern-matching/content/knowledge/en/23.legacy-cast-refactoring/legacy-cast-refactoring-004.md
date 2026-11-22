# Refactoring Nested Casts with Pattern Matching in Java 21

## 1. Goal and Context

Legacy Java code often receives `Object` or data wrapped in multiple layers, forcing it to repeatedly **check type → cast → access component → check type again**. When casts are nested, the business logic gets buried under multiple `if` layers, and expressions like `((Address) ((Customer) ((Shipment) raw).customer()).address()).city()` are hard to read and error-prone when a level is `null` or has the wrong type.

**Refactoring nested casts** means replacing chains of manual type checks and casts with **type patterns**, **nested record patterns**, and **guard clauses**, allowing Java to check the type or structure and bind a variable with the exact type at the same time. More importantly, refactoring must preserve intended behavior: return values, error precedence, exceptions, and null conditions.

Features by Java version:

- **Java 16+ (JEP 394):** `instanceof Type variable` allows type checking and variable binding at the same time.
- **Java 21+ (JEP 440):** `record patterns` and nested record patterns enable multi-level record deconstruction.
- **Java 21+ (JEP 441):** Type/record patterns can be used in `switch` with `when` guards.
- **Java 22+ (JEP 456):** Introduces the unnamed pattern `_` so unused component variables do not need names. The runnable examples in this article maintain **Java 21** compatibility.

You will learn how to migrate legacy code step by step, when to use type patterns instead of nested record patterns, how to verify semantics, and how to test the before/after implementations.

## 2. Legacy Cast Chain: Three Record Levels, Two Object Components

Suppose we have the following records:

```java
record Address(String city, String street) {}
record Customer(String name, Object address) {}
record Shipment(Object customer, int quantity) {}
```

Using `Object` for the two intermediate components simulates legacy data without strict static typing. In a newly designed system, those two components could be typed as `Customer` and `Address`; here they are `Object` so that type checking and casting are meaningful.

To extract the city and shipment quantity, a legacy approach looks like this:

```java
if (!(value instanceof Shipment)) return "Invalid structure";
Shipment shipment = (Shipment) value;

if (!(shipment.customer() instanceof Customer)) return "Invalid structure";
Customer customer = (Customer) shipment.customer();

if (!(customer.address() instanceof Address)) return "Invalid structure";
Address address = (Address) customer.address();

String city = address.city();
if (city == null || city.isBlank()) return "Missing city";
if (shipment.quantity() <= 0) return "Invalid quantity";

return "Ship " + shipment.quantity() + " for "
        + customer.name() + " to " + city;
```

Each `instanceof` checks the type, and then a `(Type) object` expression repeats that information to obtain a typed variable. While the checks guard the casts, maintenance mistakes remain easy to make: forgetting to check a level, getting the order wrong, casting the wrong object, or calling a getter on null.

This is the **checked baseline**, returning `"Invalid structure"` if the data tree does not have all three records of the expected types. When refactoring, we compare the new implementation against this baseline, including cases where `Shipment.customer()` holds a `String` or `Customer.address()` is null.

## 3. Step 1: Convert `instanceof` + Cast into a Type Pattern

Since Java 16:

```java
// Before:
if (!(value instanceof Shipment)) return "Invalid structure";
Shipment shipment = (Shipment) value;

// After:
if (!(value instanceof Shipment shipment)) return "Invalid structure";
```

The pattern `Shipment shipment` both checks the type and declares the variable `shipment` with static type `Shipment`. Applying the same transformation to all levels gives:

```java
if (!(value instanceof Shipment shipment)) return "Invalid structure";
if (!(shipment.customer() instanceof Customer customer)) return "Invalid structure";
if (!(customer.address() instanceof Address address)) return "Invalid structure";

String city = address.city();
if (city == null || city.isBlank()) return "Missing city";
if (shipment.quantity() <= 0) return "Invalid quantity";

return "Ship " + shipment.quantity() + " for "
        + customer.name() + " to " + city;
```

There are no manual casts left—only the safely bound variables `shipment`, `customer`, and `address`. Thanks to **flow scoping**, the variable remains usable **after** a guard of the form `if (!(x instanceof Type t)) return ...;`. Because the path where the pattern fails terminates with `return`, every execution path that continues downward is guaranteed to have matched the pattern.

If the failure branch only logs without exiting, the pattern variable is not definitely assigned:

```java
// DOES NOT COMPILE because the failure branch can fall through.
if (!(value instanceof Shipment shipment)) {
    System.out.println("Wrong type");
}
System.out.println(shipment.quantity());
```

Terminate the guard branch with `return`, `throw`, or restructure the code so the variable is only used where the compiler knows for certain that the pattern matched.

You can also chain type patterns using `&&`:

```java
if (value instanceof Shipment shipment
        && shipment.customer() instanceof Customer customer
        && customer.address() instanceof Address address) {
    System.out.println(address.city());
}
```

`&&` evaluates left-to-right with short-circuiting: if `Shipment` does not match, `customer()` is not read; if `Customer` does not match, `address()` is not read. The variables are available inside the `if` body once all conditions hold. However, if the business logic has multiple distinct error checks, sequential guard clauses are usually clearer than a very long `&&` expression.

## 4. Step 2: Merge Multiple Casts into a Nested Record Pattern

When **every level to be deconstructed is a record**, Java 21 lets you express the structural tree directly in a single pattern:

```java
if (!(value instanceof Shipment(
        Customer(var name, Address(var city, var street)), var quantity))) {
    return "Invalid structure";
}
if (city == null || city.isBlank()) return "Missing city";
if (quantity <= 0) return "Invalid quantity";
return "Ship " + quantity + " for " + name + " to " + city;
```

Reading from outside in:

1. `Shipment(...)` requires the outer object to be a `Shipment`, with `customer` as its first component and `quantity` as its second.
2. `Customer(...)` matches the `customer` component (even though it is declared as `Object`). If it is null or of the wrong type, the entire pattern fails to match.
3. `var name` binds the name component of `Customer`. `Address(...)` continues checking and deconstructing the `address` component.
4. `var city` and `var street` bind the two `String` components. `var quantity` binds the `int` component.
5. The code after the guard runs only when the entire record tree matches; business constraints are checked afterward.

**The number of subpatterns must match the number of components and their declaration order.** `Shipment(Customer(Address(var city)))` is invalid because it omits the corresponding component positions. In Java 21, to indicate "street is unused," you can name it `var ignoredStreet`. From Java 22 onward, the unnamed pattern `_` avoids naming the variable, though it must still occupy the exact component position.

Combining a record pattern with guard clauses keeps the code shallow: one guard validates the structure, subsequent guards validate content and business rules, and the end returns the success result. However, a longer record pattern is not always better. If you need separate messages such as `Missing customer` and `Missing address`, keep per-level checks so you know which level failed.

## 5. Preserving Nulls, Errors, and Exceptions

Correct refactoring requires specifying clearly **which inputs match, which inputs are rejected, and what the rejection result is**.

| Case | Type pattern chain | Nested record pattern | Result with example guards |
| --- | --- | --- | --- |
| `value == null` | `instanceof Shipment` is false | `Shipment(...)` does not match | `Invalid structure` |
| `value` is not `Shipment` | Outer check is false | Outer record does not match | `Invalid structure` |
| `Shipment.customer == null` | `instanceof Customer` is false | `Customer(...)` does not match | `Invalid structure` |
| `Shipment.customer` is `String` | Wrong type for `Customer` | Nested `Customer(...)` does not match | `Invalid structure` |
| `Customer.address == null` or wrong type | `instanceof Address` is false | `Address(...)` does not match | `Invalid structure` |
| `Address.city == null` | `Address` matches, component is null | `var city` binds to null | `Missing city` |
| `Address.city == " "` | `isBlank()` is true | Same as type pattern | `Missing city` |
| `Shipment.quantity <= 0`, valid structure | Final check fails | Final check fails | `Invalid quantity` |

**A null nested record differs from a null component bound with `var`.** `Address(...)` does not match when the address record itself is null, whereas `Address(var city, ...)` can match when the record exists and `city` is null. Therefore, you still need to check `city == null || city.isBlank()`. The `||` operator short-circuits, avoiding calling `isBlank()` on null.

Do not assume refactoring always preserves **exceptions**. If the legacy code performs unchecked casts:

```java
// Unsafe legacy example that can throw exceptions.
Shipment shipment = (Shipment) raw;
Customer customer = (Customer) shipment.customer();
Address address = (Address) customer.address();
String city = address.city();
```

then a wrong type can throw `ClassCastException`, and dereferencing a null intermediate record can throw `NullPointerException`. Switching to `instanceof` and returning `"Invalid structure"` **changes the error contract**. That may be an intended improvement, but callers and tests must be updated—or the original exception behavior preserved if callers depend on it.

The order of checks must also be preserved. Here, structure is checked first, then city, and finally quantity. If city is blank and quantity is negative at the same time, the baseline returns `Missing city`. Reordering the guards could return `Invalid quantity`, changing observable behavior.

## 6. Complete Example: Comparing Four Implementations on Java 21

Create the file **`NestedCastRefactorDemo.java`**:

```java
public class NestedCastRefactorDemo {
    record Address(String city, String street) {}
    record Customer(String name, Object address) {}
    record Shipment(Object customer, int quantity) {}

    static String legacy(Object value) {
        if (!(value instanceof Shipment)) return "Invalid structure";
        Shipment shipment = (Shipment) value;
        if (!(shipment.customer() instanceof Customer)) return "Invalid structure";
        Customer customer = (Customer) shipment.customer();
        if (!(customer.address() instanceof Address)) return "Invalid structure";
        Address address = (Address) customer.address();
        String city = address.city();
        if (city == null || city.isBlank()) return "Missing city";
        if (shipment.quantity() <= 0) return "Invalid quantity";
        return "Ship " + shipment.quantity() + " for " + customer.name() + " to " + city;
    }

    static String withTypePatterns(Object value) {
        if (!(value instanceof Shipment shipment)) return "Invalid structure";
        if (!(shipment.customer() instanceof Customer customer)) return "Invalid structure";
        if (!(customer.address() instanceof Address address)) return "Invalid structure";
        String city = address.city();
        if (city == null || city.isBlank()) return "Missing city";
        if (shipment.quantity() <= 0) return "Invalid quantity";
        return "Ship " + shipment.quantity() + " for " + customer.name() + " to " + city;
    }

    static String withRecordPatterns(Object value) {
        if (!(value instanceof Shipment(
                Customer(var name, Address(var city, var street)), var quantity))) {
            return "Invalid structure";
        }
        if (city == null || city.isBlank()) return "Missing city";
        if (quantity <= 0) return "Invalid quantity";
        return "Ship " + quantity + " for " + name + " to " + city;
    }

    static String withSwitch(Object value) {
        return switch (value) {
            case null -> "Invalid structure";
            case Shipment(Customer(var name, Address(var city, var street)), var quantity)
                    when city != null && !city.isBlank() && quantity > 0
                    -> "Ship " + quantity + " for " + name + " to " + city;
            case Shipment(Customer(var name, Address(var city, var street)), var quantity)
                    when city == null || city.isBlank() -> "Missing city";
            case Shipment(Customer(var name, Address(var city, var street)), var quantity)
                    -> "Invalid quantity";
            default -> "Invalid structure";
        };
    }

    public static void main(String[] args) {
        Object ok = new Shipment(new Customer("Lan", new Address("Hue", "Le Loi")), 2);
        Object badCity = new Shipment(new Customer("Mai", new Address(" ", "Street")), 1);
        Object badQuantity = new Shipment(new Customer("Minh", new Address("Hanoi", "Pho")), 0);
        Object wrongType = new Shipment("legacy customer", 4);
        Object missingAddress = new Shipment(new Customer("An", null), 1);
        Object[] cases = {ok, badCity, badQuantity, wrongType, missingAddress, null};

        for (Object input : cases) {
            String baseline = legacy(input);
            String typed = withTypePatterns(input);
            String records = withRecordPatterns(input);
            String switched = withSwitch(input);
            System.out.println(baseline + " | equal=" +
                    (baseline.equals(typed) && baseline.equals(records)
                            && baseline.equals(switched)));
        }
    }
}
```

Compile and run with JDK 21 or later, without preview features:

```bash
javac --release 21 NestedCastRefactorDemo.java
java NestedCastRefactorDemo
```

**Output:**

```text
Ship 2 for Lan to Hue | equal=true
Missing city | equal=true
Invalid quantity | equal=true
Invalid structure | equal=true
Invalid structure | equal=true
Invalid structure | equal=true
```

These are six cases: valid data, whitespace-only city, zero quantity, wrong customer type, missing address, and null input. On each line, `equal=true` means that the type pattern, nested record pattern, and switch methods all return the exact same string as the baseline.

A key detail in `withSwitch`: the `Shipment(...) when ...` branch accepts complete valid data; the `when city == null || city.isBlank()` branch catches an invalid city; the unguarded `Shipment(...)` branch handles invalid quantity. Narrower guarded branches must appear before broader branches to avoid a **dominated case label**. `case null` handles a null selector, while `default` handles invalid structures or other types.

Having all four versions match on the **six tested cases** does not automatically guarantee they behave identically on all inputs. In production code, also test wrong address types, null customer, null city, negative quantities, multiple simultaneous errors, and potential exceptions or side effects.

## 7. Step-by-Step Refactoring Workflow in a Project

1. **Capture current behavior:** Identify valid inputs, error types, exceptions, and evaluation order. Write tests for key cases before changing structure.
2. **Replace redundant casts:** Turn `if (obj instanceof Type) { Type t = (Type) obj; ... }` into `if (obj instanceof Type t) { ... }`, keeping the existing error branches.
3. **Reduce nesting with guard clauses:** Use `if (!(obj instanceof Type t)) return failure;`, ensuring the failure branch exits and the variable is only used on the guaranteed-match path.
4. **Identify records and deconstruction depth:** If inner layers are records and only a few components are needed, try a nested record pattern. If you need to know exactly which level failed, keep per-level guards.
5. **Choose `switch` when there are multiple data shapes:** With multiple subtypes or multiple record cases, a `switch` expression or statement with dedicated `case` branches can be clearer than a chain of `if` statements.
6. **Verify semantics:** Compare return values, exceptions, null checks, error precedence, accessor invocations, and any potential side effects.
7. **Finalize once verified:** Run the relevant tests and remove obsolete casts or branches; avoid leaving two parallel implementations in production code.

You do not need to convert the entire cast tree at once. You can refactor the outer cast first, run tests, and then move to the next level. This is especially useful in large repositories or code with many callers.

## 8. When to Keep Type Patterns Instead of Nested Record Patterns?

Nested record patterns can only deconstruct **records**. For regular classes, you cannot write `LegacyCustomer(Address(...))` as if the class were a record.

For example, suppose a codebase defines a regular class `LegacyCustomer` with a `getAddress()` getter:

```java
if (!(raw instanceof LegacyCustomer customer)) {
    return "Invalid customer";
}
if (!(customer.getAddress() instanceof Address address)) {
    return "Invalid address";
}
String city = address.city();
```

This snippet illustrates combining type patterns with getters for regular classes; it is not standalone because it depends on the application's `LegacyCustomer` definition. Even when one level is a regular class and the next level is a record, you can combine a type pattern at the class level with a record pattern on the record component.

Sometimes you already have a variable of type `Shipment` and only need `shipment.quantity()`. In that case, a direct accessor call is simpler than creating a record pattern just to extract a single field. Pattern matching is most valuable at **untyped or loosely typed boundaries**, where you need a runtime check followed immediately by data extraction.

**Generic limitation:** Checking `raw instanceof java.util.List<String>` is invalid when `raw` is `Object` because the `String` type argument cannot be verified at runtime due to type erasure. Use `List<?>` instead and check each element:

```java
if (raw instanceof java.util.List<?> values) {
    for (Object item : values) {
        if (item instanceof String name) {
            System.out.println(name);
        }
    }
}
```

Pattern matching does not bypass generic type-safety rules. If legacy code contains unchecked casts, clarify the data contract before replacing them.

## 9. Be Careful with Evaluation Order and Side Effects

A record can define custom accessors, and a regular class can implement getters with logic, exceptions, or side effects. When converting multiple accessor calls into a nested record pattern, the number of reads and their evaluation order may differ. For immutable DTOs/records with simple accessors, this difference rarely matters; for code with caching, logging, mutable state, or custom accessors, testing is essential.

Do not force all conditions into a single pattern if the system needs distinct messages such as `Missing customer`, `Missing address`, and `Missing city`. In that case, a chain of type patterns and guard clauses may be longer, but it makes clear exactly which level failed.

If a record has many components and you only need a few values, you must still include every position in the pattern. Java 21 allows naming unused components like `var ignoredStreet`. The unnamed pattern `_` is only available starting in Java 22; do not use it when compiling with `javac --release 21`.

## 10. Common Pitfalls

| Issue | Cause | How to fix |
| --- | --- | --- |
| Using `shipment` after `if (!(raw instanceof Shipment shipment))` without exiting the failure branch | The pattern variable is not definitely assigned. | `return` or `throw` on failure, or use the variable inside the matching branch. |
| Skipping a type check at an intermediate level | A direct cast can throw `ClassCastException`. | Keep the type pattern or nested record pattern at the appropriate level. |
| Checking only the outer record and calling a getter on a null child record | Dereferencing null can throw `NullPointerException`. | Check the child record or deconstruct it with a nested pattern. |
| Assuming `var city` is always non-null | The `Address` record may be valid while its `city` component is null. | Keep `city == null || city.isBlank()`. |
| Writing `Shipment(Customer(Address(var city)))` | Missing component positions compared to the record declaration. | Include all subpatterns in the exact declaration order. |
| Using a record pattern on a regular class | Java 21 does not support arbitrary deconstruction for regular classes. | Use a type pattern and accessors. |
| Placing a general `switch` branch before a `when` branch | The narrower branch is dominated (unreachable). | Place specific guarded branches first. |
| Omitting `case null` when a null selector must be handled | `default` does not handle null in the desired way. | Add `case null` or check for null before the switch. |
| Replacing legacy exceptions with default values without reviewing the API | Changes the caller's error contract. | Document intended behavior and update tests/callers if needed. |
| Ignoring condition check order | May return a different error message when multiple conditions fail together. | Preserve guard order or change it intentionally. |
| Assuming generic type arguments are checked at runtime | Type erasure does not verify `List<String>`. | Use `List<?>` and check elements individually. |
| Testing only the happy path | Nulls, wrong types, negative quantities, and blank cities go untested. | Compare both valid inputs and failure cases. |

## 11. Practice Exercise

Given the records:

```java
record Position(int row, int column) {}
record Location(Object position) {}
record Device(Object location) {}
```

Requirements for `Object raw`:

- If it does not match the chain `Device → Location → Position`, return `"invalid structure"`.
- If it matches but `row < 0`, return `"invalid row"`.
- If it matches and `row` is non-negative, return `"row="` followed by the row value.

**Checked-cast version:**

```java
static String oldDescribe(Object raw) {
    if (!(raw instanceof Device)) return "invalid structure";
    Device device = (Device) raw;
    if (!(device.location() instanceof Location)) return "invalid structure";
    Location location = (Location) device.location();
    if (!(location.position() instanceof Position)) return "invalid structure";
    Position position = (Position) location.position();
    if (position.row() < 0) return "invalid row";
    return "row=" + position.row();
}
```

**Record pattern version (Java 21):**

```java
static String describe(Object raw) {
    if (!(raw instanceof Device(Location(Position(var row, var column))))) {
        return "invalid structure";
    }
    if (row < 0) return "invalid row";
    return "row=" + row;
}
```

When writing `Device(Location(Position(var row, var column)))`, the pattern matches from the outer record down to the deepest component. `column` is bound but unused because Java 21 requires all component positions. This version preserves the exact error messages of the checked baseline for the following inputs:

- `new Device(new Location(new Position(3, 7)))` → `row=3`.
- `new Device(new Location(new Position(-1, 7)))` → `invalid row`.
- `new Device(new Location(null))` → `invalid structure`.
- `new Device("not a location")` → `invalid structure`.
- `null` → `invalid structure`.

The methods in this exercise are snippets meant to be placed in a class alongside the three declared records. A standalone program with `main`, the `javac` command, and stdout output was shown in full in Section 6.

**Challenge:** If you need to distinguish a missing `Location` error from a missing `Position` error, write three per-level guard clauses using type patterns and keep the two error messages separate.

## 12. Key Takeaways

- For legacy casts, start by replacing `instanceof Type` + `(Type)` with a **type pattern** and a safely typed variable.
- When multiple layers are all records, you can use a **nested record pattern** to check and extract components in one step; all component positions and declaration order must match.
- **Guard clauses** handle failure paths early and keep the success logic at a shallow indentation level; pay attention to pattern variable flow scoping.
- A **null nested record** causes that level's deconstruction pattern to fail to match, whereas a `var` component inside a matched record can still be null.
- Always verify **error behavior, exceptions, check order, and side effects**, not just line-count reduction.
- Use `switch` when there are multiple meaningful types or branches; use a linear chain of guards when checking a single structure.

**References:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 456 — Unnamed Variables & Patterns](https://openjdk.org/jeps/456), [Java 21 JLS — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
