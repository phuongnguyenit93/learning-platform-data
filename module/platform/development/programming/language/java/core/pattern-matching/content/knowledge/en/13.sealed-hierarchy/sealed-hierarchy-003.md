# Sealed hierarchy supports exhaustive `switch` in Java

**Topic:** Java Core Pattern Matching → Sealed hierarchy  
**Version:** Sealed classes/interfaces are a standard feature since Java 17 (JEP 409); pattern matching for `switch` and `when` guards are standard since Java 21 (JEP 441). The practice program uses **JDK 21+**.

## 1. The problem: how does the compiler know all subtypes have been handled?

When a method accepts an ordinary interface like `Payment`, Java usually cannot know for sure all classes that might implement that interface now or in the future. Therefore, a `switch` expression using type patterns needs a way to cover the remaining values, such as `default`, if the cases have not proven *exhaustiveness*.

With a **sealed hierarchy**, the designer publicly declares the **set of permitted direct subtypes**. The compiler can analyze this closed type tree to verify whether the `case` labels cover all non-null cases.

Example:

```java
sealed interface Payment permits Card, Transfer, Voucher {}

record Card(String lastFour) implements Payment {}
record Transfer(String reference) implements Payment {}
record Voucher(int points) implements Payment {}
```

Here `Payment` permits only three direct subtypes: `Card`, `Transfer`, and `Voucher`. They are `record`s, so they are implicitly `final` and cannot be subclassed further.

A `switch` on a variable with static type `Payment` can be written as:

```java
static String category(Payment payment) {
    return switch (payment) {
        case Card card -> "CARD";
        case Transfer transfer -> "TRANSFER";
        case Voucher voucher -> "VOUCHER";
    };
}
```

This is an **illustrative method** that must be placed together with the type declarations above inside a valid Java class/scope. The compiler proves that all three non-null groups are handled, so the `switch` expression **does not need `default`**.

**Key takeaway:** a sealed hierarchy does not "automatically run all cases". It provides enough information about the type system for the compiler to check coverage; the developer must still write appropriate labels for each branch.

## 2. `sealed`, `permits`, and permitted subtypes

### 2.1. `sealed` closes the list of direct subtypes

The declaration:

```java
sealed interface Payment permits Card, Transfer, Voucher {}
```

means only the classes/interfaces declared as valid direct subtypes of `Payment` are allowed to `implements Payment` or `extends Payment`. With this example, you cannot simply add `class CryptoPayment implements Payment {}` elsewhere and expect the compiler to accept it: that type is not in the list of permitted direct subclasses.

In Java, permitted types must also satisfy location rules: in a named module, they must belong to the same module as the sealed type; if not using a named module, they must be in the same package. Do not treat `permits` as a list of arbitrary class names across any module.

### 2.2. Each direct subtype must specify an extension policy

A class directly extending a sealed class, or a class/interface directly extending/implementing a sealed interface, must declare the continuation strategy of the type tree:

- **`final`**: disallows further subclassing. A `record` is implicitly `final`, so you do not write `final record`.
- **`sealed`**: continues closing the tree at the next level with a set of permitted subtypes.
- **`non-sealed`**: opens that branch to further subtypes, even though the parent branch remains sealed.

Illustrative example:

```java
sealed interface Outcome permits Success, Failure, Later {}

record Success(String message) implements Outcome {}
record Failure(int code) implements Outcome {}

// This branch is intentionally open for extension:
non-sealed interface Later extends Outcome {}

record Queued(String ticket) implements Later {}
record Retried(int seconds) implements Later {}
```

`Outcome` remains closed at the **direct level**: its direct subtypes are only `Success`, `Failure`, and `Later`. However, `Later` is `non-sealed`, so other implementations of `Later` can be added later. This matters when designing a `switch`: `case Later later` is enough to cover that entire open branch without listing every sub-implementation.

**Do not confuse `sealed` with `enum`.** An `enum` closes a set of constant values; a sealed hierarchy closes a set of direct type variants and allows each subtype to hold its own data/behavior.

## 3. Why does `switch` become exhaustive without `default`?

Java 21 uses the information about permitted subtypes when checking coverage of a `switch` with a sealed-type selector.

Suppose:

```java
static String describe(Outcome outcome) {
    return switch (outcome) {
        case Success success -> "SUCCESS:" + success.message();
        case Failure failure -> "FAILURE:" + failure.code();
        case Later later -> "LATER";
    };
}
```

The `Success` branch matches `Success` objects. The `Failure` branch matches `Failure`. The `Later` branch covers **every object whose runtime type implements `Later`**, including `Queued`, `Retried`, or any new subtype added later. Those three cases cover the three permitted direct branches of `Outcome`.

Because the compiler verifies all type groups, no `default` is needed for the non-null values of `Outcome`. This does not mean `switch` automatically handles `null`; see section 6.

### Comparison with a non-sealed interface

```java
interface OpenEvent {}
record Created(String id) implements OpenEvent {}
record Removed(String id) implements OpenEvent {}
```

The two visible records **do not prove** that every future `OpenEvent` value belongs to `Created` or `Removed`:

```java
// DOES NOT COMPILE as a switch expression:
static String unsafe(OpenEvent event) {
    return switch (event) {
        case Created created -> "CREATE";
        case Removed removed -> "REMOVE";
    };
}
```

You can add `default`, or use a catch-all type pattern according to your design policy. With the sealed `Outcome`, the compiler has stronger information thanks to `permits`, which is why it can prove exhaustiveness using the specific branches.

## 4. When a subtype is missing, the compiler reports an error

Suppose:

```java
sealed interface Message permits Email, Sms {}
record Email(String subject) implements Message {}
record Sms(String number) implements Message {}
```

The following is **not a valid program** because `Sms` is missing:

```java
static String broken(Message message) {
    return switch (message) {
        case Email email -> "EMAIL";
    };
}
// Compile error: the switch expression does not cover all possible input values.
```

The proper fix for a closed type domain:

```java
static String repaired(Message message) {
    return switch (message) {
        case Email email -> "EMAIL";
        case Sms sms -> "SMS";
    };
}
```

Or if business logic truly wants a general fallback, use `default`. However, for a sealed hierarchy where each subtype **must** have its own logic, listing the specific subtypes without `default` usually provides a major benefit: missing cases are caught by the compiler when developers modify the type system.

## 5. A `when` guard does not automatically cover an entire subtype

A guarded type pattern only matches when **both the type pattern and the guard expression** succeed.

```java
case Voucher voucher when voucher.points() < 0 -> "INVALID";
```

This branch only handles negative `Voucher` values; it does not handle `Voucher(0)`, `Voucher(100)`, etc. Therefore, to achieve exhaustiveness, after any specialized guarded branches there must be a branch that covers the rest of the subtype:

```java
case Voucher voucher when voucher.points() < 0 -> "INVALID";
case Voucher voucher -> "VALID:" + voucher.points();
```

Similarly with `Card`:

```java
case Card card when card.lastFour() == null -> "CARD_MISSING";
case Card card -> "CARD:" + card.lastFour();
```

Place the specialized branch first, and the unguarded branch of the same type afterward. If reversed:

```java
// DOES NOT COMPILE: the guarded branch is dominated.
case Card card -> "ANY_CARD";
case Card card when card.lastFour() == null -> "CARD_MISSING";
```

The first `case Card card` already accepts every non-null `Card`. The later branch can never be selected.

**Do not equate dominance with exhaustiveness:** dominance asks whether a branch is shadowed by an earlier branch; exhaustiveness asks whether all valid branches sufficiently cover the required data domain. A `switch` can lack exhaustiveness without any dominance error, or have `default` and still have a dominance error.

## 6. `null` is a separate case, even when all subtypes are covered

Keep this clearly in mind:

- `case Card card`, `case Transfer transfer`, and `case Voucher voucher` handle matching **non-null** objects.
- `null` is not an instance of `Card`, `Transfer`, or `Voucher`.
- The compiler can consider a `switch` expression exhaustive by sealed hierarchy even without writing `case null`.
- At runtime, if the selector is `null` without an appropriate `null`-handling label, `switch` normally throws `NullPointerException`, even when a regular `default` is present.

If a null input is a valid scenario, choose an explicit policy:

```java
static String safe(Payment payment) {
    return switch (payment) {
        case null -> "NO_PAYMENT";
        case Card c -> "CARD";
        case Transfer t -> "TRANSFER";
        case Voucher v -> "VOUCHER";
    };
}
```

Or explicitly reject null:

```java
case null -> throw new IllegalArgumentException("payment is required");
```

This rejection is an API policy, not something the compiler infers automatically from `sealed`.

**Note on null components:** a `record Card(null)` is still a `Card` object and will match `case Card c`. A sealed hierarchy does not guarantee that a record's components are non-null. Before calling `c.lastFour().length()`, you must guard against a null component; the practice program below has a dedicated case for this situation.

## 7. Should you write `default` with a sealed hierarchy?

You can, but you should decide based on the application contract. Example:

```java
static String withDefault(Payment payment) {
    return switch (payment) {
        case Card c -> "CARD";
        case Transfer t -> "TRANSFER";
        default -> "OTHER";
    };
}
```

Here `default` makes the expression exhaustive even though `Voucher` is not explicitly listed. If a permitted subtype `GiftCard` is added in the future, that branch may also be absorbed by `default` without the compiler requiring a dedicated case. This is **reasonable** when the application genuinely allows a general fallback; however, it can be **dangerous** when a new subtype requires dedicated business logic and goes unnoticed.

Comparison:

| Design approach | Benefit | Trade-off |
| --- | --- | --- |
| List all subtype branches, **no `default`** | Compiler catches unhandled new subtypes upon recompilation | Must update logic when the hierarchy changes |
| Include `default -> "UNKNOWN"` | Provides a fallback policy for unclassified values | Easily hides a forgotten new branch |
| Include `default -> throw ...` | Does not silently accept unexpected values | Still does not force writing dedicated logic for a new subtype at compile time |
| Broad `case Payment p` | Provides a `Payment`-typed variable for the remainder | Can cause subsequent subtype cases to be dominated |

For closed, critical business domains (transaction states, validation results, message types), it is often worth considering **omitting `default`** for stronger compile-time checks.

However, do not omit `default` merely out of stylistic preference: on an open-type selector (`Object` or a non-sealed interface), the compiler may still require another coverage mechanism.

## 8. Nested sealed subtypes and `non-sealed` branches

A sealed hierarchy does not have to stop at a single level:

```java
sealed interface Vehicle permits Bicycle, MotorVehicle {}
record Bicycle(int gears) implements Vehicle {}

sealed interface MotorVehicle extends Vehicle permits Car, Bus {}
record Car(int seats) implements MotorVehicle {}
record Bus(int capacity) implements MotorVehicle {}
```

You can handle `Vehicle` using cases for `Bicycle`, `Car`, and `Bus` when the compiler can deduce that the nested closed branches are covered. If you only write `case Car c` and `case Bicycle b`, then `Bus` is missing. Another option is `case MotorVehicle motor` to cover both `Car` and `Bus` if you do not need to split them.

With a `non-sealed` branch, you **do not need to, and usually cannot**, list every potential implementer:

```java
sealed interface Outcome permits Success, Failure, Later {}
non-sealed interface Later extends Outcome {}
```

To make `switch (Outcome)` exhaustive without `default`, use a case that covers `Later`:

```java
case Later later -> "LATER";
```

This remains valid even with `Later` implementations added in the future. **Trade-off:** the compiler helps detect new direct subtypes of `Outcome`, but **does not force you to distinguish each new implementation under the `Later` branch**. If each `Later` kind needs distinct handling, consider keeping that branch `sealed` instead of `non-sealed`.

## 9. Complete Java 21 program: sealed switch without default

The practice program includes two structures:

1. `Payment`: sealed with three final records, cases with `when`, and a final unguarded branch for each subtype.
2. `Outcome`: sealed with two final records and one `non-sealed` interface named `Later`. The `case Later l` branch covers implementations of `Later`.

The program includes self-tests with expected outputs, requiring no JUnit or external libraries.

**Create the file `SealedSwitchExhaustiveDemo.java`:**

```java
public class SealedSwitchExhaustiveDemo {
    sealed interface Payment permits Card, Transfer, Voucher {}
    record Card(String lastFour) implements Payment {}
    record Transfer(String reference) implements Payment {}
    record Voucher(int points) implements Payment {}

    sealed interface Outcome permits Success, Failure, Later {}
    record Success(String message) implements Outcome {}
    record Failure(int code) implements Outcome {}
    non-sealed interface Later extends Outcome {}
    record Queued(String ticket) implements Later {}
    record Retried(int delaySeconds) implements Later {}

    static String paymentLabel(Payment payment) {
        return switch (payment) {
            case null -> "PAYMENT_NULL";
            case Card c when c.lastFour() == null -> "CARD_MISSING";
            case Card c -> "CARD:" + c.lastFour();
            case Transfer t -> "TRANSFER:" + t.reference();
            case Voucher v when v.points() < 0 -> "VOUCHER_INVALID";
            case Voucher v -> "VOUCHER:" + v.points();
        };
    }

    static String outcomeLabel(Outcome outcome) {
        return switch (outcome) {
            case null -> "OUTCOME_NULL";
            case Success s -> "SUCCESS:" + s.message();
            case Failure f -> "FAILURE:" + f.code();
            case Later l -> "LATER:" + l.getClass().getSimpleName();
        };
    }

    static void check(String name, String actual, String expected) {
        if (!actual.equals(expected)) {
            throw new AssertionError(name + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(name + "=" + actual);
    }

    public static void main(String[] args) {
        check("null-payment", paymentLabel(null), "PAYMENT_NULL");
        check("card-null", paymentLabel(new Card(null)), "CARD_MISSING");
        check("card", paymentLabel(new Card("1234")), "CARD:1234");
        check("transfer", paymentLabel(new Transfer("TR-7")),
                "TRANSFER:TR-7");
        check("voucher-negative", paymentLabel(new Voucher(-1)),
                "VOUCHER_INVALID");
        check("voucher-zero", paymentLabel(new Voucher(0)), "VOUCHER:0");
        check("voucher", paymentLabel(new Voucher(50)), "VOUCHER:50");

        check("null-outcome", outcomeLabel(null), "OUTCOME_NULL");
        check("success", outcomeLabel(new Success("saved")),
                "SUCCESS:saved");
        check("failure", outcomeLabel(new Failure(404)), "FAILURE:404");
        check("queued", outcomeLabel(new Queued("Q-1")), "LATER:Queued");
        check("retried", outcomeLabel(new Retried(10)), "LATER:Retried");

        System.out.println("ALL CASES PASSED");
    }
}
```

Compile and run:

```bash
javac --release 21 SealedSwitchExhaustiveDemo.java
java SealedSwitchExhaustiveDemo
```

**Exact standard output:**

```text
null-payment=PAYMENT_NULL
card-null=CARD_MISSING
card=CARD:1234
transfer=TRANSFER:TR-7
voucher-negative=VOUCHER_INVALID
voucher-zero=VOUCHER:0
voucher=VOUCHER:50
null-outcome=OUTCOME_NULL
success=SUCCESS:saved
failure=FAILURE:404
queued=LATER:Queued
retried=LATER:Retried
ALL CASES PASSED
```

### Output explanation

- `paymentLabel(null)`: enters `case null`, without assuming `null` is one of the three subtypes.
- `new Card(null)`: the guarded `Card` branch catches the `lastFour == null` component before general handling.
- `new Card("1234")`: the null guard is false, so it enters the unguarded `Card` branch.
- `new Transfer("TR-7")`: matches the `Transfer` branch.
- `new Voucher(-1)`: matches the negative-value guard; `0` and `50` go into the general `Voucher` branch. Because of this general branch, `Voucher` is fully covered for exhaustiveness.
- `Outcome` has `Success`, `Failure`, or `Later`, so the three corresponding branches are exhaustive. Both `Queued` and `Retried` belong to `Later`, returning `LATER:Queued` and `LATER:Retried`.
- `check` uses `equals` to compare against the expected result. If any result is wrong, the program throws `AssertionError`; `ALL CASES PASSED` is only printed after all 12 checks succeed.

None of the `switch` expressions in the program use `default`, because the sealed types are covered by type patterns, combined with `case null` for null inputs.

## 10. Test matrix needed when a sealed hierarchy grows

| Input | Expected pattern | Reason to test |
| --- | --- | --- |
| `null` | `case null` | Exhaustiveness does not mean null is automatically accepted |
| `new Card(null)` | Guarded `Card` | Record components can be null |
| `new Card("1234")` | Unguarded `Card` | When the guard is false, a handling branch still exists |
| `new Transfer("TR-7")` | `Transfer` | Second direct subtype is covered |
| `new Voucher(-1)` | Guarded `Voucher` | Separate negative domain |
| `new Voucher(0)` | Unguarded `Voucher` | Zero boundary and remaining values |
| `new Success("saved")` | `Success` | Direct subtype |
| `new Failure(404)` | `Failure` | Direct subtype |
| `new Queued("Q-1")` | `Later` | Non-sealed branch covered by a type pattern |
| `new Retried(10)` | `Later` | Another implementation is also covered |

**Two types of testing serve different roles:**

- **Compiler checks**: intentionally remove `case Transfer` or add a new permitted subtype without updating the switch, then recompile. The compiler reports missing exhaustiveness.
- **Runtime checks**: verify that when all cases are present, the right value is selected, guards are in the right order, results are meaningful, and null is handled properly.

Adding `case Transfer` just to make the compiler error go away does not prove the code handles transfer logic correctly. Therefore, a dedicated test for `Transfer` is still needed.

## 11. `switch` expressions, enhanced statements, and module changes

In Java 21, a **`switch` expression** must be exhaustive. An **enhanced `switch` statement** (such as a statement using pattern cases) also has an exhaustiveness requirement; do not assume a statement can omit cases just because it does not return a value.

```java
static void printPayment(Payment payment) {
    switch (payment) {
        case Card c -> System.out.println("Card");
        case Transfer t -> System.out.println("Transfer");
        case Voucher v -> System.out.println("Voucher");
    }
}
```

This is an **illustrative** method to be placed in a class with the `Payment` declaration as above. It is an enhanced switch statement covering all subtypes, without needing `default`. Even so, if `null` is passed, the lack of `case null` can still lead to a `NullPointerException`.

An advanced note on **separate compilation**: exhaustiveness is checked by the compiler based on the hierarchy it sees **at compile time**. If a dependency changes its subtypes without old client code being recompiled accordingly, a `switch` that was once exhaustive can encounter an unexpected state at runtime (for example, `MatchException` under the conditions of the Java 21 specification). Therefore, when changing public sealed classes across multiple modules, rebuild and run tests for dependent modules; compile-time exhaustiveness **is not a guarantee that mismatched binaries are safe**.

## 12. Common mistakes and fixes

| Mistake or misconception | Consequence | Correct approach |
| --- | --- | --- |
| Missing a `case` for a permitted subtype | `switch` expression/enhanced statement may fail to compile | List all subtypes or use an intentional fallback |
| Writing only `case Voucher v when v.points() < 0` | Non-negative vouchers are not covered | Add an unguarded `case Voucher v` |
| Placing `case Card c` before `case Card c when ...` | The specialized branch is dominated | Place the guarded branch before the general branch |
| Believing `sealed` means all inputs are non-null | Misses null selectors and null components | Define a `case null` policy; guard components |
| Always adding `default` to every sealed switch | May hide a new subtype that has not been handled individually | Consider exhaustive switches without `default` |
| Assuming `non-sealed Later` needs no case because only two implementations exist now | The compiler cannot infer all implementations of an open branch from the currently visible list | Use `case Later l` to cover the branch |
| Assuming `permits` lists all descendants to infinite depth | Confuses direct subtypes with indirect subtypes | Understand each `sealed`/`final`/`non-sealed` branch |
| Forgetting `final`, `sealed`, or `non-sealed` on a regular direct subtype class | Fails sealed inheritance rules | Specify the policy explicitly; records are implicitly final |
| Writing a new class that directly `implements Payment` outside the list | Rejected by the compiler | Intentionally update `permits` and related switches |
| Using Java 17 to compile Java 21 pattern `switch` | Does not support standard syntax such as `when` | Use JDK 21+ and `javac --release 21` |
| Confusing dominance with exhaustiveness | Fixing case order while still missing branches, or adding `default` while a case remains dominated | Analyze each rule separately |
| Thinking the compiler guarantees correct business logic | Code can still return the wrong information in a valid case | Unit tests and boundary tests for each subtype |

## 13. Practice exercises

1. Create `sealed interface Event permits Created, Deleted` with two records `Created(String id)` and `Deleted(String id)`. Write a `switch` expression returning a result for both subtypes without `default`; explain why the compiler accepts it.
2. Remove the `case Deleted d` branch in exercise 1, compile, and read the exhaustiveness error. Add back the missing branch instead of rushing to write `default`.
3. Add `record Updated(String id) implements Event` and include `Updated` in `permits`. Observe how the compiler requires updating the existing `switch`. Write a test for the new subtype.
4. Write `case Created c when c.id() == null` followed by `case Created c` to handle a null component. Swap the order of the two branches and explain the dominance error.
5. Try a `switch` without `case null` on `Event`. Even though the switch is exhaustive for non-null values, explain the behavior when `null` is passed. Add a branch that makes the policy explicit.
6. Create a multi-level hierarchy where `sealed interface Vehicle` has a subtype `sealed interface MotorVehicle`. Write cases for the leaf branches. Try adding a new leaf branch and recompiling.
7. Create a `non-sealed interface Extra extends Event` branch and add it to `permits`. Use `case Extra e` to cover current and future implementations; compare this with trying to list every implementation.
8. Write two versions of a sealed switch: one listing all cases without `default`, and one using `default`. Add a permitted subtype and compare how the compiler requires code changes.
9. Convert `paymentLabel` into a `switch` expression returning a record `Decision(String code, String message)`. Write assertions comparing the record instead of just checking strings; ensure each subtype behaves correctly.
10. Run `SealedSwitchExhaustiveDemo` and compare all 13 lines of standard output. Try `Voucher(-1)`, `Voucher(0)`, and `Card(null)` to explain why a guard cannot replace an unguarded branch.

**Completion criteria:** able to independently design a sealed hierarchy with valid `permits`; understand the roles of `final`/`sealed`/`non-sealed`; write exhaustive Java 21 `switch` constructs without `default` when appropriate; explain `null` handling, guards, and caveats when a hierarchy grows; have both compile-time and runtime tests.

**Official references:**

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JLS Java SE 21 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [JLS Java SE 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
