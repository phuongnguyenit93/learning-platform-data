# Choosing Between Patterns and Polymorphism

## 1. Two Different Approaches, Not Absolute Rivals

When working with a supertype that has multiple subtypes, Java allows two approaches:

- **Polymorphism:** sending the same message to an object through a method on the parent interface/class; the concrete type decides how to execute it. Calling code usually does not have to check which subtype the object belongs to.
- **Pattern matching:** checking whether a value matches a type or structure to be handled, optionally binding variables and choosing the corresponding action. Java 21 supports type patterns, record patterns, and pattern matching in `switch`.

For example, a delivery domain has `Courier` (home delivery) and `Pickup` (station pickup). There are two different questions:

1. "How does a delivery method calculate its fee?" — this can be **core behavior** belonging to each delivery type, suitable for polymorphism.
2. "How does the admin screen want to display different descriptions based on each delivery structure?" — this can be a **classification and data transformation** serving a specific context, suitable for pattern matching.

**Selection principle:** Do not choose an approach just because it takes fewer lines. Ask: **does the logic belong to the responsibility of the object itself or to the party observing/classifying the object?**, and **does the set of subtypes need to be extended independently?**

## 2. Polymorphism: Behavior Lives in the Object

Suppose the model is:

```java
sealed interface Delivery permits Courier, Pickup {
    int fee();
}

record Courier(int distanceKm) implements Delivery {
    @Override
    public int fee() {
        return 10 + 2 * distanceKm;
    }
}

record Pickup(String stationCode) implements Delivery {
    @Override
    public int fee() {
        return 5;
    }
}
```

These are illustrative Java 17+ declarations; the complete example in a later section adds validation.

A user of the interface simply calls:

```java
static int calculateFee(Delivery delivery) {
    return delivery.fee();
}
```

There is no need to write:

```java
// Classifying types just to call each subtype's behavior again:
// often makes logic depend directly on concrete types.
static int calculateFeeVerbose(Delivery delivery) {
    if (delivery instanceof Courier courier) {
        return courier.fee();
    }
    if (delivery instanceof Pickup pickup) {
        return pickup.fee();
    }
    throw new IllegalArgumentException("Unknown delivery");
}
```

If both subtypes already implement `fee()`, checking the type just to call `fee()` on each subtype is **redundant**. It forces external code to know every delivery type, even though the interface already provides the exact contract to hide that difference.

### Advantages of Polymorphism

- **Centralized behavior:** `Courier`'s fee formula lives in `Courier`, `Pickup`'s formula lives in `Pickup`; callers only depend on `Delivery.fee()`.
- **Easy subtype extension in an open system:** with a regular interface, adding a new implementation may not require modifying places that only call the common method, as long as the implementation follows the contract.
- **Encapsulated invariants:** each implementation can validate its own input data and calculation logic, avoiding having multiple callers reimplement the same rules.
- **Easy to call and test through the contract:** code using `Delivery` does not need to know too many internal details of the subtypes.

### Limitations of Polymorphism

If there is a **new task, independent of the domain's essence** — such as rendering a specialized report format, generating UI labels, or exporting a format dedicated to a partner system — adding more methods to the interface can force every subtype to carry unnecessary responsibilities.

Every time an **abstract method** is added to an interface implemented by many units, existing implementations usually must be updated upon recompilation. A `default` method can reduce the impact in some cases, but does not solve every design or compatibility issue. If every screen wants its own method on the domain type, the model easily becomes bloated.

## 3. Pattern Matching: Classifying from the Operation's Perspective

With Java 21, a data transformation can be written using a `switch` expression:

```java
static String label(Delivery delivery) {
    return switch (delivery) {
        case Courier(int distanceKm) when distanceKm > 10 ->
                "Giao xa: " + distanceKm + " km";
        case Courier(int distanceKm) ->
                "Giao tận nhà: " + distanceKm + " km";
        case Pickup(String stationCode) ->
                "Nhận tại điểm " + stationCode;
        case null ->
                "Chưa chọn phương thức";
    };
}
```

Here `label` belongs to the **display context**, not the fee calculation rule. It inspects the record and extracts the needed components:

- `Courier(int distanceKm)` checks the type and extracts the distance from the record's component.
- `when distanceKm > 10` is a **guard** evaluated after the pattern matches. The more specific case is placed before the unguarded `Courier` case to avoid being dominated by the broader branch.
- `Pickup(String stationCode)` deconstructs the pickup station code.
- `case null` handles a `null` selector explicitly, instead of letting the program accidentally throw a `NullPointerException`.

Because `Delivery` in the example is a **sealed interface** with only two direct subtypes, `Courier` and `Pickup`, and both are final records, the Java 21 compiler can verify that both non-null types are covered by the unguarded cases. In this example, no `default` is needed.

**Strengths of pattern matching:** opinionated external transformations can be added in the reporting layer, adapters, or UI layer without forcing domain records to know about every context that consumes them. A concise `switch` also makes the entire set of outcomes clear side by side.

**Weaknesses:** if multiple modules each write a `switch` to recompute a shared business rule per subtype, the rule is easily duplicated and can drift out of sync. Pattern matching does not by itself replace the responsibility of encapsulating behavior.

## 4. Why Does a Sealed Interface Change the Comparison?

`sealed interface` vs. a regular `interface` is an **independent decision, yet strongly related** to choosing between patterns and polymorphism.

### Closed or Controlled Domains

`sealed interface Delivery permits Courier, Pickup` specifies the direct subtypes that may implement the root type. When all branches are known, a `switch` expression listing type/record patterns can be checked by the compiler for **exhaustiveness**.

If the domain owner later adds `Drone` to `permits`, `switch` expressions without a catch-all branch can be reported as missing a case upon recompilation, forcing developers to decide how to handle `Drone` in each task. This can be an advantage: domain changes produce a clear signal at classification sites.

You should not add `default` to every `switch` over a closed hierarchy just to silence errors when a new subtype is added. `default` often hides the opportunity for the compiler to remind you to update a policy that needs exhaustive handling.

### Open Domains for Plugins

For example:

```java
interface DeliveryPlugin {
    String providerName();
}
```

It is impossible to know in advance all implementations that partners will provide. When handling a `DeliveryPlugin`, calling behavior through the interface is usually beneficial:

```java
static String provider(DeliveryPlugin plugin) {
    return plugin.providerName();
}
```

A `switch` that tries to list a few concrete implementations of an open interface needs a way to handle other implementations. Code relying on `case SomePlugin`, `case OtherPlugin` easily develops a fragile dependency on the current list. If a third party can add a new type without notice, polymorphism usually shields most callers better than enumerating subtypes.

**Note:** Being sealed does not force you to use `switch`; a sealed interface can still perfectly well declare polymorphic methods. Conversely, `instanceof` and type patterns can still be used with open interfaces. `sealed` simply provides extra information to the type system about the **permitted set of subtypes**.

## 5. Choosing by Dimension of Change: Adding Subtypes or Adding Operations?

Domain evolution can be viewed along two dimensions:

| Future Change | Design Favoring Polymorphism | Design Favoring Pattern/`switch` |
| --- | --- | --- |
| **Adding a subtype** | If the interface is open and the behavioral contract is stable, the new type implements the methods itself; general callers usually stay unchanged. | `switch` statements/expressions enumerating subtypes may need new cases; in a sealed hierarchy, the compiler helps detect many missing sites. |
| **Adding a new operation** | If the operation belongs to the contract, it usually requires adding a method and implementing it in subtypes (or another design to avoid bloating the interface). | An independent `switch` function can be added in the consuming module without modifying each subtype. |
| **Changing a shared business rule** | The rule lives in each implementation; callers do not duplicate logic. | If the rule is scattered across multiple `switch` blocks, many places may need to be updated. |
| **Reading multiple variants of closed data** | Shared behavior or Visitor can be used if appropriate. | Pattern matching is concise with clear branches; especially useful with records and sealed types. |
| **Allowing independent plugins** | The polymorphic contract of an open interface is usually more favorable. | Listing concrete types struggles to keep up with new plugins; requires a general/fallback branch. |

This is a **code organization trade-off**, not a formula with a single solution. Cases with **many subtypes added frequently** but **few, stable operations** lean toward polymorphism. Cases with a **closed, rarely changing set of subtypes** but **many independent data-reading operations** lean toward pattern matching or operation-oriented data organization.

For example, a compiler's AST usually consists of a controlled set of nodes; multiple processing passes such as pretty-printing, analysis, and code generation may need to access the structure by node type. Conversely, a contract for an exporter plugin usually needs to allow new implementations without forcing calling code to recognize each plugin individually.

## 6. Complete Runnable Java 21 Example: Combining Both

To compare the same result, the program below intentionally includes both a polymorphic `fee()` and a `feeByPattern()` that calculates the fee using `switch`. **In real production code, you should not maintain two copies of a fee calculation formula.** Here `feeByPattern()` only helps observe both options; once a design decision is made, keep **a single source of truth** for the fee rule. `label()` is a reasonable example of keeping pattern matching dedicated to presentation logic.

Create the file **`PatternVsPolymorphismDemo.java`**:

```java
public class PatternVsPolymorphismDemo {
    sealed interface Delivery permits Courier, Pickup {
        int fee();
    }

    record Courier(int distanceKm) implements Delivery {
        Courier {
            if (distanceKm < 0) {
                throw new IllegalArgumentException("distanceKm must be >= 0");
            }
        }

        @Override
        public int fee() {
            return 10 + 2 * distanceKm;
        }
    }

    record Pickup(String stationCode) implements Delivery {
        Pickup {
            java.util.Objects.requireNonNull(stationCode, "stationCode");
        }

        @Override
        public int fee() {
            return 5;
        }
    }

    // Illustrate an alternative: switch performs the fee calculation.
    static int feeByPattern(Delivery delivery) {
        return switch (delivery) {
            case Courier(int distanceKm) -> 10 + 2 * distanceKm;
            case Pickup(String stationCode) -> 5;
            case null -> throw new IllegalArgumentException("Missing delivery");
        };
    }

    // Display context: use patterns to extract data from each record.
    static String label(Delivery delivery) {
        return switch (delivery) {
            case Courier(int distanceKm) when distanceKm > 10 ->
                    "Giao xa: " + distanceKm + " km";
            case Courier(int distanceKm) ->
                    "Giao tận nhà: " + distanceKm + " km";
            case Pickup(String stationCode) ->
                    "Nhận tại điểm " + stationCode;
            case null ->
                    "Chưa chọn phương thức";
        };
    }

    static void show(Delivery delivery) {
        System.out.println(label(delivery));
        System.out.println("Phí đa hình: " + delivery.fee());
        System.out.println("Phí pattern: " + feeByPattern(delivery));
    }

    public static void main(String[] args) {
        show(new Courier(4));
        show(new Pickup("P-01"));
        show(new Courier(12));
        System.out.println(label(null));
    }
}
```

Compile and run with **JDK 21 or later** (no `--enable-preview` needed):

```bash
javac -encoding UTF-8 PatternVsPolymorphismDemo.java
java PatternVsPolymorphismDemo
```

Output:

```text
Giao tận nhà: 4 km
Phí đa hình: 18
Phí pattern: 18
Nhận tại điểm P-01
Phí đa hình: 5
Phí pattern: 5
Giao xa: 12 km
Phí đa hình: 34
Phí pattern: 34
Chưa chọn phương thức
```

Explanation of each case:

1. `new Courier(4)` is a home delivery type, so `fee()` returns `10 + 2 * 4 = 18`. `feeByPattern()` matches the `Courier` record and gives the same result. In `label()`, `distanceKm > 10` is false, so the remaining `Courier` case is selected.
2. `new Pickup("P-01")` has a fixed fee of `5` in both approaches. The pattern `Pickup(String stationCode)` extracts the pickup station code to build a custom label.
3. `new Courier(12)` has a fee of `34`; because `12 > 10`, the case with `when` produces the `"Giao xa"` label.
4. `label(null)` returns `"Chưa chọn phương thức"`. `show` is only called with non-null objects; if `delivery.fee()` were called on `null`, Java would throw a `NullPointerException`, whereas `feeByPattern(null)` is designed to throw an `IllegalArgumentException`. These two different null-handling behaviors are an API choice, **not an inherent property of patterns or polymorphism**. To compare or perform an equivalent refactor, the null contract must be aligned first.

In this example, `Courier` has a constructor checking that the distance is non-negative, and `Pickup` requires a non-null station code. Record patterns have typed components, so maintaining input invariants keeps cases clear and avoids missing-data scenarios that would otherwise need separate handling.

## 7. An Important Criterion: Which Layer Does the Logic Belong To?

### When to Lean Toward Polymorphism

Suppose operations such as `pay()`, `reserve()`, or `fee()` are **behaviors that every subtype must provide**, have stable rules, and are called from many places. A good pattern is:

```java
static int totalFee(java.util.List<? extends Delivery> deliveries) {
    int total = 0;
    for (Delivery delivery : deliveries) {
        total += delivery.fee();
    }
    return total;
}
```

This is an illustrative method, assuming `Delivery` is already defined. The caller simply invokes the common contract without asking `delivery instanceof Courier` before deciding how to calculate. If you truly want to compute large totals safely against overflow, you can use `Math.addExact` or an appropriate numeric type; that is a separate domain decision.

If, just out of preference for patterns, you move `fee()` logic into multiple `switch` blocks in the service layer, services end up knowing too much about subtypes. The obvious consequence is that changing a fee formula requires searching many places.

### When to Lean Toward Pattern Matching

Tasks that **read structure** to transform into an external representation are often very natural with `switch`:

- Displaying different labels for domain variants.
- Converting a closed event type into a DTO for reporting or an external protocol.
- Classifying a finite set of records to produce statistics.
- Performing a new independent transformation without adding methods to every record.

When `Delivery` consists of only two records controlled by the domain, a `switch` with clear cases can be easier to understand than adding `delivery.adminViewLabel()` to the interface just because one admin screen needs that data.

**Exception:** If the transformation function is itself a long-term responsibility of the object and is used in many places, putting it on the interface or in a named service is still worth considering. The goal is to establish **a single source of truth for behavior**, not necessarily to pick a single syntax.

## 8. When Should You Combine Them?

In real projects, the choice is rarely "100% patterns" or "100% polymorphism".

A good combined model might look like:

- **Domain:** interfaces with behavioral contracts; subtypes implement them and validate their own invariants.
- **Application service:** invokes behavior through the interface, knowing little about subtypes unless necessary.
- **Presentation/reporting:** uses type/record patterns in `switch` to produce display data or specific formats.
- **Boundary:** receives external data, validates types and structure before converting into domain objects with stable contracts.

The example in section 6 uses `delivery.fee()` for fee calculation behavior and `label(delivery)` for descriptions. This is a **responsible combination**, rather than duplicating two fee-calculation paths everywhere.

An easy rule of thumb: **"Call a method when you want the object to act; match a pattern when you want to know which case the object belongs to in order to perform an external transformation."** This principle is an architectural guideline, not a rigid rule. A system may have performance, compatibility, layering, or testing constraints that make another organization more suitable.

## 9. Common Mistakes When Choosing

| Design Mistake | Impact | Remedy |
| --- | --- | --- |
| Checking types just to call a method already on the interface | Callers depend on subtypes unnecessarily. | Call the method through the interface to leverage polymorphic dispatch. |
| Scattering the same business formula across multiple `switch` blocks | Easy to get inconsistent results and miss branches when rules change. | Establish a single source of truth, usually a domain method or a clearly defined service. |
| Adding every reporting/display task to the domain interface | The interface bloats; subtypes become responsible for out-of-domain contexts. | Use a separate mapper/service, where pattern matching can be applied. |
| Using `switch` to enumerate subtypes of an open interface without a fallback | Cannot handle new implementations. | Use shared behavior or an appropriate catch-all branch. |
| Unconditionally adding `default` to every `switch` over a sealed domain | Can hide missing handling for a new subtype. | Let the compiler check exhaustiveness when every type must be updated. |
| Placing a general case before a specific case | Later cases are dominated and may fail to compile. | Place specific/guarded patterns before broader branches. |
| Assuming `sealed` automatically validates data invariants | Component values can still be invalid or null if unchecked. | Validate in constructors/boundaries; handle null according to the contract. |
| Refactoring from polymorphism to patterns and changing null/exception behavior | No longer equivalent; can break the API. | Lock down the contract and write tests for both error paths and boundary data. |
| Choosing solely based on line count or guessed performance | Ignores maintenance cost and domain role. | Prioritize proper responsibility first, then benchmark if performance matters. |

## 10. Refactoring and Testing Scenarios

### From Redundant Type Checks to Polymorphism

Before:

```java
static int fee(Delivery delivery) {
    if (delivery instanceof Courier courier) {
        return courier.fee();
    }
    if (delivery instanceof Pickup pickup) {
        return pickup.fee();
    }
    throw new IllegalArgumentException("Unsupported delivery");
}
```

After, when `Delivery` already has the `fee()` contract:

```java
static int fee(Delivery delivery) {
    return delivery.fee();
}
```

This is illustrative code for calls with **non-null objects belonging to the defined type hierarchy**. Error paths for `null` and unsupported types must be evaluated separately before claiming a refactor is strictly behavior-preserving.

### From Many Small Visitors to a Data Transformation

If a task only needs to convert a closed set of records into an external description, a `switch` inside a mapper method can be more readable than adding a method to every subtype or maintaining a large visitor interface. However, if the project already has a visitor with significant architectural meaning (e.g., needing double dispatch, stateful traversal, or older Java versions), do not automatically delete it just because pattern matching exists.

### Recommended Test Suite

- For **each subtype**, test the polymorphic contract (`fee()`) and key transformations (`label()`) on normal values.
- For **boundary values**, test `when` guards (e.g., `distanceKm = 10` vs. `11`), negative number invariants, empty cases, and `null`.
- For **hierarchy changes**, recompile `switch` blocks that rely on exhaustiveness, avoiding hiding missing branches with unnecessary `default` cases.
- For **open interfaces**, test with a new implementation or a fake implementation to verify callers do not depend on a concrete type list.
- For **refactors**, compare both return values and exception types when behavior preservation is required. Do not compare only success cases.

## 11. Self-Check

Suppose an application has:

```java
sealed interface Message permits Email, Sms {
    String send();
}
record Email(String address) implements Message {
    public String send() { return "Sent email"; }
}
record Sms(String phone) implements Message {
    public String send() { return "Sent SMS"; }
}
```

**Exercise 1:** A service needs to send a message. Should it write `if (m instanceof Email) ... else if (...)` or `m.send()`?

**Answer:** Prefer `m.send()` because the behavior is already defined in the `Message` contract. Dispatching by subtype repeats a decision that polymorphism already solves.

**Exercise 2:** A screen needs to display `"Email đến địa chỉ ..."` or `"SMS đến số ..."`, but the domain should not know about UI wording. What should be used?

**Answer:** A separate mapper with `switch` and record patterns, for example:

```java
static String display(Message message) {
    return switch (message) {
        case Email(String address) -> "Email đến " + address;
        case Sms(String phone) -> "SMS đến " + phone;
        case null -> "Chưa chọn";
    };
}
```

This illustrative example requires Java 21. The subtype set `Email`, `Sms` is controlled, so all cases can be checked exhaustively; `case null` expresses the UI policy when no object is present.

**Exercise 3:** If partners must be allowed to add a new `Message` type in their own module, what needs to be reconsidered?

**Answer:** Evaluate whether the contract should become an **open interface**, use a **`non-sealed` branch**, or separate the extension point from the closed domain. Any `switch` that previously relied on a finite set of subtypes must also be reviewed. This is an architectural decision, not merely editing `permits`.

**Conclusion:** **Polymorphism** fits when you want subtypes to each execute a behavior belonging to a contract; **pattern matching** fits when an operation needs to classify and read data from a set of variants, especially records in a sealed hierarchy. To keep code readable and maintainable, consider **where the logic's responsibility lies**, **expected dimensions of change**, **null rules**, **exhaustiveness guarantees**, and **how many places must change as the domain evolves**. The two techniques usually complement each other better than they completely replace one another.
