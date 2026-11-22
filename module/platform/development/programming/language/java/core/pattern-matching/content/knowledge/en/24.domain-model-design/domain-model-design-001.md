# Choosing `interface` vs. `sealed interface`

## 1. The Design Question: Open or Closed Type Domain?

When modeling a domain in Java, both a regular `interface` and a `sealed interface` can express **a shared contract for multiple object types**. The core difference lies in who has the right to extend the hierarchy:

- **Regular `interface` (open interface):** other classes or interfaces can implement or extend the contract under standard access and module rules. The interface author does not enumerate all implementations up front.
- **`sealed interface` (closed or controlled hierarchy):** the contract author specifies **the allowed direct subtypes**. An allowed subtype can close its branch completely, continue restricting its branch, or intentionally open its branch.

For example, in a payment system:

- **Payment outcomes** in the system core consist of only three states: `Approved`, `Declined`, and `Pending`. If this is a domain-owned set of variants that requires exhaustive handling, `sealed interface` is a good candidate.
- **Payment providers** may come from internal integrations, partners, or plugins that do not yet exist when writing the code. If external code should be able to add implementations, a regular `interface` may be more suitable.

There is no rule that "`sealed` is always better" or "whenever you use pattern matching you must use `sealed`." Choose based on **the actual extensibility of the domain**, ownership of the subtypes, and how the application consumes those subtypes.

## 2. Regular Interface: Open for New Implementations

An open contract:

```java
interface PaymentProvider {
    String name();
}

record DomesticProvider(String name) implements PaymentProvider {}
record PartnerProvider(String name) implements PaymentProvider {}
```

Another module or integration layer can add a new implementation, as long as it satisfies Java's rules for access, modules, and interface methods:

```java
final class PluginProvider implements PaymentProvider {
    @Override
    public String name() {
        return "Plugin-X";
    }
}
```

These snippets are example declarations that can be combined in the same program. When a contract is open, handling code must accept the fact that **unlisted implementations may appear**.

Example with pattern matching for `switch` in Java 21:

```java
static String providerLabel(PaymentProvider provider) {
    return switch (provider) {
        case DomesticProvider p -> "Nội địa: " + p.name();
        case PartnerProvider p -> "Đối tác: " + p.name();
        case null -> "Chưa có nhà cung cấp";
        default -> "Khác: " + provider.name();
    };
}
```

Because `PaymentProvider` is an open interface, handling only `DomesticProvider` and `PartnerProvider` **does not prove that every future subtype is handled**. The `default` branch here defines fallback behavior for other implementations. Another option is to use `case PaymentProvider p` after the specific branches to create a non-null catch-all branch.

**When to prefer an open interface:**

- The feature is an **extension point**, SPI (Service Provider Interface), or plugin API.
- Multiple implementations are expected from other teams or third parties.
- The list of implementations changes frequently and is not controlled by a single module.
- The API primarily invokes shared behavior such as `provider.authorize(...)` or `provider.name()`, without needing to distinguish every subtype.
- Tests or mocks need to add implementations independently of existing subtypes.

In return, the compiler cannot use an **open implementation list** to prove that a `switch` listing a few concrete subtypes covers the entire domain.

## 3. Sealed Interface: Controlling Direct Subtypes

Modeling payment outcomes:

```java
sealed interface PaymentOutcome permits Approved, Declined, Pending {}

record Approved(long transactionId) implements PaymentOutcome {}
record Declined(int reasonCode) implements PaymentOutcome {}
record Pending(int secondsToRetry) implements PaymentOutcome {}
```

Here, `PaymentOutcome` is the root type. The three records are **the permitted direct implementations**, and records are implicitly `final`, so they cannot be subclassed further.

If another class writes:

```java
// DOES NOT COMPILE: Unknown is not in the permits list.
// record Unknown(int code) implements PaymentOutcome {}
```

the compiler will reject directly implementing `PaymentOutcome`, because that type is not in the `permits` set. This is a **type-system constraint enforced at compile time**, not merely a documentation convention.

In a **named module**, the permitted direct subtypes must belong to the same module as the sealed type. If using the **unnamed module**, the permitted direct subtypes must be in the same package. The examples in this article place the types in the same enclosing class, so they do not run into these package/module organization rules.

The `sealed interface` modifier does not mean **every branch is permanently non-extensible**. Each permitted direct subtype must declare how the hierarchy continues:

- A **class** can be `final` to close the branch, `sealed` to continue listing subtypes, or `non-sealed` to reopen the branch. A `record` is already implicitly `final`.
- A sub-**interface** can be `sealed` to continue restricting or `non-sealed` to allow new implementations.
- `non-sealed` cannot be applied arbitrarily to an interface that has no corresponding `sealed` supertype; `non-sealed` is the choice to reopen a branch that is currently controlled.

`permits` lists **direct subtypes**, not every descendant at arbitrary depth. If the direct subtypes are in the same compilation unit, the compiler can infer the list in some cases; explicitly writing `permits` still often helps readers see the boundaries of the domain.

## 4. Major Value: `switch` Exhaustiveness and Pattern Matching

For the `PaymentOutcome` root type above, a `switch` expression can handle all permitted variants:

```java
static String outcomeLabel(PaymentOutcome outcome) {
    return switch (outcome) {
        case Approved(long id) -> "Thành công #" + id;
        case Declined(int code) -> "Từ chối mã " + code;
        case Pending(int seconds) -> "Chờ " + seconds + " giây";
        case null -> "Chưa có kết quả";
    };
}
```

This is a **Java 21** example that can be placed alongside the record declarations in the previous section. The `case` labels use **record patterns**: they both check the subtype and deconstruct its component into a strongly typed variable.

Because `PaymentOutcome` directly permits only `Approved`, `Declined`, and `Pending`, and all three are `final` records, the compiler has enough information to determine that all **non-null** forms have a branch. `case null` handles a `null` selector separately. There is no need to write a `default` branch just to "cover all cases."

Design benefits:

1. **The set of variants is expressed in the type system**, not only in documentation.
2. **The compiler checks exhaustiveness** of the `switch` expression.
3. When the domain is extended with a new subtype, `switch` statements/expressions relying on exhaustiveness may require updates; this is a useful signal to review business rules.
4. Record patterns can extract data directly in the `case`, avoiding repeated casts and accessor calls.

A subtle point: `sealed` helps the compiler understand **permitted subtypes**, but that does not mean the compiler understands all **value** constraints. If you write:

```java
case Pending(int seconds) when seconds > 0 -> "Đang chờ";
```

then this branch only handles `Pending` instances satisfying `seconds > 0`. You must still have a branch for `Pending` with `seconds <= 0` (or an equivalent catch-all branch); otherwise, the set of cases may not be exhaustive. Therefore, do not use `when` guards as a substitute for exhaustiveness checking.

Similarly, a `sealed interface` does not automatically forbid `null`, negative numbers, or invalid data in components. If the domain requires `secondsToRetry >= 0`, add validation in the constructor or at the data boundary. **Sealed controls the shape of the hierarchy; it does not automatically guarantee all object invariants.**

## 5. Sealed Does Not Have to Close Every Branch: Using `non-sealed` Intentionally

A system may want to keep core event types finite, while opening up the group of events coming from partners:

```java
sealed interface PaymentEvent permits CoreEvent, PartnerEvent {}

record CoreEvent(int code) implements PaymentEvent {}

non-sealed interface PartnerEvent extends PaymentEvent {
    String code();
}

record WebhookEvent(String code) implements PartnerEvent {}
```

`CoreEvent` is a `final` record; no subtypes of `CoreEvent` can be added. `PartnerEvent` is a **permitted direct branch** marked `non-sealed`, so other types are allowed to implement `PartnerEvent` under standard Java rules.

When handling `PaymentEvent`:

```java
static String eventLabel(PaymentEvent event) {
    return switch (event) {
        case CoreEvent(int code) -> "Core: " + code;
        case PartnerEvent partner -> "Partner: " + partner.code();
        case null -> "Không có event";
    };
}
```

The compiler can still verify exhaustiveness, because the `case PartnerEvent partner` branch covers **every implementation in that open branch**. Writing only `case WebhookEvent webhook` would not be sufficient to represent all future implementations of `PartnerEvent`.

This pattern is useful when the domain has clear boundaries: **major groups are controlled**, while some groups allow extension. However, do not overcomplicate the hierarchy just to use all three keywords `sealed`, `non-sealed`, and `final`; only use it when different branches genuinely have different open/closed requirements.

## 6. Complete Runnable Java 21 Example

Create the file **`ChooseInterfaceOrSealedDemo.java`**:

```java
public class ChooseInterfaceOrSealedDemo {
    // Closed outcome hierarchy: only three direct subtypes.
    sealed interface PaymentOutcome permits Approved, Declined, Pending {}

    record Approved(long transactionId) implements PaymentOutcome {}
    record Declined(int reasonCode) implements PaymentOutcome {}
    record Pending(int secondsToRetry) implements PaymentOutcome {}

    // Extension point: external code can provide new providers.
    interface PaymentProvider {
        String name();
    }

    record DomesticProvider(String name) implements PaymentProvider {}
    record PartnerProvider(String name) implements PaymentProvider {}

    // Hybrid hierarchy: sealed root, non-sealed on one branch.
    sealed interface PaymentEvent permits CoreEvent, PartnerEvent {}
    record CoreEvent(int code) implements PaymentEvent {}

    non-sealed interface PartnerEvent extends PaymentEvent {
        String code();
    }

    record WebhookEvent(String code) implements PartnerEvent {}

    static String outcomeLabel(PaymentOutcome outcome) {
        return switch (outcome) {
            case Approved(long id) -> "Thành công #" + id;
            case Declined(int code) -> "Từ chối mã " + code;
            case Pending(int seconds) -> "Chờ " + seconds + " giây";
            case null -> "Chưa có kết quả";
        };
    }

    static String providerLabel(PaymentProvider provider) {
        return switch (provider) {
            case DomesticProvider p -> "Nội địa: " + p.name();
            case PartnerProvider p -> "Đối tác: " + p.name();
            case null -> "Chưa có nhà cung cấp";
            default -> "Khác: " + provider.name();
        };
    }

    static String eventLabel(PaymentEvent event) {
        return switch (event) {
            case CoreEvent(int code) -> "Core: " + code;
            case PartnerEvent partner -> "Partner: " + partner.code();
            case null -> "Không có event";
        };
    }

    public static void main(String[] args) {
        System.out.println(outcomeLabel(new Approved(1024L)));
        System.out.println(outcomeLabel(new Declined(403)));
        System.out.println(outcomeLabel(new Pending(15)));
        System.out.println(outcomeLabel(null));

        System.out.println(
                providerLabel(new DomesticProvider("Nội bộ")));
        System.out.println(
                providerLabel(new PartnerProvider("Đối tác A")));

        PaymentProvider plugin = new PaymentProvider() {
            @Override
            public String name() {
                return "Plugin-X";
            }
        };
        System.out.println(providerLabel(plugin));
        System.out.println(providerLabel(null));

        System.out.println(eventLabel(new CoreEvent(7)));
        System.out.println(eventLabel(new WebhookEvent("W-1")));
        System.out.println(eventLabel(null));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac ChooseInterfaceOrSealedDemo.java
java ChooseInterfaceOrSealedDemo
```

Expected output:

```text
Thành công #1024
Từ chối mã 403
Chờ 15 giây
Chưa có kết quả
Nội địa: Nội bộ
Đối tác: Đối tác A
Khác: Plugin-X
Chưa có nhà cung cấp
Core: 7
Partner: W-1
Không có event
```

Explanation:

- The first four lines come from the **closed hierarchy** `PaymentOutcome`. The three records are fully specified by `permits`, so the `switch` expression does not need `default`; the `null` case has its own branch.
- The next two lines identify the known implementations of `PaymentProvider`.
- `plugin` is an **anonymous** implementation of the open interface; it does not belong to `DomesticProvider` or `PartnerProvider`. Therefore, `default` returns `Khác: Plugin-X`. This way of adding an implementation cannot be used to directly implement `PaymentOutcome` unless the new type is listed in `permits`.
- `providerLabel(null)` selects `case null`, not `default`.
- The last three lines use the **hybrid** hierarchy `PaymentEvent`. `CoreEvent` is deconstructed using a record pattern; `WebhookEvent` is an implementation of the extensible `PartnerEvent` branch and is handled by the type pattern `PartnerEvent partner`.

In this program, the records are declared nested inside the main class; Java allows this organization. When splitting across real files and modules, the package, module, and visibility rules for `sealed` must be followed.

## 7. Key Considerations Before Choosing

### 7.1. Stability of the Domain

If the set of variants is **truly finite and owned by the core module**, `sealed` expresses an architectural invariant: only permitted subtypes participate in the model. Typical examples include variants of a *result*, *AST node*, *internal command*, or a state with a well-defined set of choices.

If the domain requires **the ability to register new types** that the core library cannot predict, a regular interface is usually appropriate—for example, plugins, drivers, providers, or integration adapters.

You should not choose `sealed` merely because **there are currently only two implementations**. "Currently only two" is different from "by contract there will only be two or a controlled set."

### 7.2. Who Owns the Subtypes?

With `sealed`, the developer of the root type controls the set of direct subtypes. This fits an internal domain owned by a single module.

With an open interface, other modules or teams can add implementations. If a library publishes an interface for clients to extend, switching from an open interface to `sealed` later can **break existing implementations' source code** because they are no longer permitted to implement it directly.

### 7.3. Impact of Adding a New Type

| Scenario | Regular interface | Sealed interface |
| --- | --- | --- |
| Adding a new implementation | Can be implemented if visibility and contract requirements are met. | Cannot be implemented directly unless permitted; usually requires updating `permits` and module organization rules. |
| `switch` listing a few subtypes | Needs a catch-all branch or `default` if the compiler cannot see full coverage. | Can be checked for exhaustiveness based on permitted subtypes. |
| Adding a subtype to the domain | Handling code is not forced by the compiler to update everywhere if a fallback already exists. | Recompiled `switch` expressions/statements may report missing branches when the subtype set changes. |
| Integrating unforeseen plugins | More flexible. | Requires a pre-designed `non-sealed` branch or another extension mechanism. |
| Domain boundaries | Relies heavily on conventions and API docs. | Expressed directly in Java's inheritance/implementation rules. |

Adding a permitted subtype is a domain model change that affects handling code and compatibility. When deploying separately compiled modules, do not assume upgrading a hierarchy without synchronizing dependent code is always safe; compile-time exhaustiveness is an advantage when recompiling and re-checking all call sites.

### 7.4. Behavioral Polymorphism vs. Data Classification

If subtypes primarily perform **shared behavior** through interface methods—for example, `provider.authorize(request)`—then the code may not need a type-discriminating `switch`. Using an open interface makes sense if the contract is designed as an extension point.

If many parts of the application need to **classify data structures** to handle each variant differently, `sealed` + `record` + pattern matching lets the compiler know the valid types and check branch coverage. Still, if that classification is repeated in too many places, consider moving the behavior into domain methods instead of turning every operation into a large `switch`.

## 8. Common Misconceptions

1. **"Sealed means every subclass is final."** False. `sealed` controls **direct** subtypes. A permitted subtype can be `sealed` or `non-sealed` to continue or reopen the hierarchy; a `record` is implicitly final.
2. **"Records must be used with sealed."** False. A `record` can implement a regular interface, a `sealed interface`, or any valid sub-interface. Records and `sealed` solve two different needs: representing data and restricting a hierarchy.
3. **"Using sealed eliminates `default` in every `switch`."** Not necessarily. It depends on the selector, patterns, `when` guards, `non-sealed` branches, and exhaustiveness rules. The compiler checks the cases expressed in code, not arbitrary business conditions.
4. **"Sealed automatically validates values inside a record."** False. `record Pending(int secondsToRetry)` still allows negative numbers if there is no validation. `sealed` only restricts **subtype kinds**, not data validity.
5. **"Open interfaces cannot be used with pattern matching."** False. Type patterns and record patterns still work; the difference is that the compiler cannot infer all future implementations from an open interface alone.
6. **"`default` always handles `null` as well."** Do not rely on that. With pattern matching for `switch`, `null` has specific rules; the examples in this article use `case null` when the selector can be `null`.
7. **"Direct implementations can be added in any module when a sealed interface has `permits`."** Incorrect. Permitted direct subtypes are constrained to the same named module, or the same package in the unnamed module.
8. **"Sealed makes code always compatible when adding a new state."** Incorrect. Adding a variant may require updating `switch` expressions, tests, serialization, APIs, and dependent modules. That is an architectural impact to manage, not a flaw of `sealed`.

## 9. Design Selection Checklist

Before choosing, answer the following:

1. Is the set of variants a **finite domain definition** or merely the implementations that exist today?
2. Who is allowed to add implementations: the core module, other internal modules, or third parties as well?
3. If a new subtype appears, should the system **force handling updates** or run through a shared contract?
4. Do you need the compiler to guarantee that `switch` expressions do not miss any permitted type?
5. Are there requirements for plugin integration or independent versioning across modules?
6. Is a **controlled open branch** genuinely needed to balance a closed domain and an extension point?
7. Which data invariants need to be checked in constructors/APIs rather than relying on `sealed`?

**Practical decision rules:**

- Choose **`sealed interface`** when the set of subtypes is clearly controlled, domain-meaningful, and requires exhaustiveness when classifying.
- Choose **regular `interface`** when you want to publish a contract so unforeseen implementations can participate.
- Choose **`sealed` combined with a `non-sealed` branch** when only part of the hierarchy is allowed to be extended, and that branch has a clear enough contract to be handled generically.

## 10. Java Versions and Self-Check

- **Sealed classes/interfaces** and **records** have been standard features since **Java 17** (records became standard in Java 16). The type models in this article can be used with JDK 17.
- **Pattern matching for `switch` and record patterns** have been standard since **Java 21**. The complete runnable program above requires JDK 21 and does not need `--enable-preview`.
- If a project only has Java 17, you can still use `sealed interface`, but handle classification with `instanceof`/type patterns or polymorphic methods instead of Java 21 record patterns in `switch`.

**Scenario 1:** An e-commerce application has exactly three core-contract states: `Created`, `Paid`, and `Cancelled`. Whenever a state is added, routing code must be reviewed. **Suggestion:** `sealed interface` with `final` records representing the states.

**Scenario 2:** A library allows clients to write new exporters without modifying the library. **Suggestion:** an open `interface Exporter` with a shared method such as `export(data)`, avoiding a `switch` that tries to enumerate all exporters.

**Scenario 3:** Internal events have only two groups: `SystemEvent` and `PluginEvent`; developers want to allow plugins to extend only the second group. **Suggestion:** a `sealed` root with a permitted `non-sealed PluginEvent` branch; `switch` statements/expressions on the root type handle the entire plugin group via `case PluginEvent e`.

**Key takeaway:** The main difference between `interface` and `sealed interface` is **who can extend the hierarchy and how much of the subtype set the compiler knows**. Good design matches domain boundaries, plugin needs, and the API change lifecycle; `sealed` together with pattern matching provides strong exhaustiveness checking, but is only worth using when the model genuinely requires a controlled set of variants.
