# Testing Exhaustive `switch` in Java 21

## 1. Learning Objectives

A `switch` is called **exhaustive** when, according to the static type of the selector expression (*selector*) and Java's type coverage rules, the set of `case` labels can handle every value that the compiler requires to be covered. For `sealed` hierarchies, `enum`s, and record patterns, exhaustiveness is especially useful: when a domain model gains a new variant, the compiler can detect places where handling has not been updated.

However, **compiling successfully does not mean the logic of every branch is correct**. Testing an exhaustive switch requires two independent layers:

1. **Compile-time verification:** intentionally omit a `case` or add a subtype and confirm that `javac` rejects the non-exhaustive `switch`.
2. **Runtime behavior testing:** construct each valid variant, verify the result of each `case`, `when` conditions, `null` values, nested records, and edge-case data scenarios.

In this lesson, we use **Java 21**: `sealed` types have been stable since Java 17 (JEP 409), while pattern matching for `switch` (JEP 441) and record patterns (JEP 440) are standard features as of Java 21. Examples compile with `javac --release 21`, without needing `--enable-preview`.

## 2. Which `switch` Constructs Must Be Exhaustive?

It is inaccurate to simply say "every `switch` in Java must be exhaustive." Different constructs have different rules.

| Construct | Exhaustiveness Requirement in Java 21 | Notes |
| --- | --- | --- |
| **`switch` expression** (`return switch (...) { ... };`) | Required | Must produce an appropriate result for every input within the required coverage domain |
| **Enhanced `switch` statement** (a statement with patterns or enhanced features) | Required | A pattern `switch` statement must also be exhaustive |
| **Legacy `switch` statement** with constant cases only, e.g., enum `case OPEN` | Not required for legacy compatibility | Can omit enum constants and still compile; this is not proof of full coverage |
| `switch` expression on a **sealed hierarchy** | Can be exhaustive without `default` | When covering all possible subtypes |
| `switch` expression on an **enum** | Can be exhaustive without `default` | When listing every enum constant |
| `switch` on `Object` with a few type patterns | Usually not exhaustive | Requires a pattern covering all non-null values, or an appropriate `default` |

In a `switch` expression, `case` branches can return an expression or use a block with `yield`; the compiler checks both the result type and exhaustiveness. In an enhanced `switch` statement, branches can perform actions without returning a value, but must still cover the input type.

**`default` does not automatically cover `null`:** with a reference selector, `switch` normally throws `NullPointerException` when the value is `null` unless an appropriate `null`-handling branch is present. Type exhaustiveness does not mean the selection automatically handles `null`.

## 3. Two Different Promises: "All Cases Covered" vs. "Correct Behavior"

Suppose a domain has payment results:

```java
sealed interface PaymentResult
        permits Approved, Declined, Pending {}

record Approved(String id, long cents) implements PaymentResult {}
record Declined(String id, String reason)
        implements PaymentResult {}
record Pending(String id) implements PaymentResult {}
```

A `switch` with cases `Approved`, `Declined`, `Pending` and no `default` can be verified as exhaustive by the compiler because the root `PaymentResult` is `sealed` and all three records are `final`.

However, all three branches could mistakenly return the string `"approved"` and **the compiler would still accept it**. Therefore:

- **Exhaustiveness is proven by the compiler:** every variant of the static type has a handling path.
- **Outputs and side effects are proven by tests:** each variant is routed properly and produces the right business outcome.
- **Version safety is proven by integration tests:** whether older consumers, newer libraries, wire data, and rollout paths remain compatible.

Tests that merely measure 100% code coverage cannot replace compile-time exhaustiveness either: an overly broad `default` can execute and mask the absence of dedicated handling for a new subtype.

## 4. Complete Example: Testing Each Case Without External Libraries

The program below uses a `sealed interface`, `record`s, record patterns, and a `when` guard. It tests **two different paths for `Approved`**, the other two subtypes, and `null`.

Save to `ExhaustiveSwitchDemo.java`:

```java
public class ExhaustiveSwitchDemo {
    sealed interface PaymentResult
            permits Approved, Declined, Pending {}

    record Approved(String id, long cents) implements PaymentResult {}
    record Declined(String id, String reason)
            implements PaymentResult {}
    record Pending(String id) implements PaymentResult {}

    static String render(PaymentResult value) {
        return switch (value) {
            case Approved(var id, var cents) when cents >= 1000 ->
                    "large:" + id;

            case Approved(var id, var cents) ->
                    "approved:" + id + ":" + cents;

            case Declined(var id, var reason) ->
                    "declined:" + id + ":" + reason;

            case Pending(var id) ->
                    "pending:" + id;

            case null ->
                    "missing";
        };
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + " actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        check("approved-small", "approved:A-1:500",
                render(new Approved("A-1", 500)));

        check("approved-large", "large:A-2",
                render(new Approved("A-2", 1500)));

        check("declined", "declined:B-1:limit",
                render(new Declined("B-1", "limit")));

        check("pending", "pending:C-1",
                render(new Pending("C-1")));

        check("null", "missing", render(null));

        System.out.println("ALL 5 PASS");
    }
}
```

Run with JDK 21 or later:

```bash
javac --release 21 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo
```

**Exact stdout:**

```text
PASS approved-small
PASS approved-large
PASS declined
PASS pending
PASS null
ALL 5 PASS
```

In this program, `check` throws `AssertionError` directly on mismatch, so it **does not depend** on whether the `-ea` flag is enabled for Java's `assert` statement.

### Why Is This `switch` Exhaustive?

- `PaymentResult` is `sealed`, permitting only `Approved`, `Declined`, and `Pending`.
- Each subtype is a `record`, meaning no further subclasses of that record exist.
- The first `Approved` branch has `when cents >= 1000`, so it **does not cover all** `Approved` values; the second unguarded `Approved` branch handles the remainder.
- `Declined` and `Pending` each have a case.
- `case null` establishes an explicit policy for a `null` selector; this is a separate behavioral test, not a substitute for handling subtypes.

**Branch order matters.** The guarded `Approved` branch precedes the general `Approved` branch. If reversed, the specific branch would be *dominated* by the broader case and cause a compile error or become unreachable under dominance rules.

### Example Test Matrix

| Input | Selected Case | Expected Result |
| --- | --- | --- |
| `Approved("A-1", 500)` | Unguarded `Approved` | `approved:A-1:500` |
| `Approved("A-2", 1500)` | `Approved` with `when` true | `large:A-2` |
| `Declined("B-1", "limit")` | `Declined` | `declined:B-1:limit` |
| `Pending("C-1")` | `Pending` | `pending:C-1` |
| `null` | `case null` | `missing` |

This test matrix exercises the **actual execution paths** of the current cases. The compiler accepting the `switch` without `default` confirms compile-time exhaustiveness; the two checks complement each other.

## 5. Negative Compile Test: Adding a Subtype While Intentionally Omitting Its `case`

A strong test for domain design is proving that **missing a variant breaks the build**. Use a separate negative-compile fixture, **never mixed into production sources**.

Save the following intentionally invalid snippet as `MissingCase.java`:

```java
public class MissingCase {
    sealed interface Signal permits Go, Stop, Pause {}

    record Go() implements Signal {}
    record Stop() implements Signal {}
    record Pause() implements Signal {}

    static int code(Signal value) {
        return switch (value) {
            case Go go -> 1;
            case Stop stop -> 2;
            // Intentionally omitting case Pause.
        };
    }
}
```

Run:

```bash
javac --release 21 MissingCase.java
```

**Expected result:** `javac` returns a **non-zero exit code**, and the error message indicates that the `switch` does not cover all possible inputs, for example:

```text
the switch expression does not cover all possible input values
```

Exact diagnostic wording can vary across `javac` versions, so tooling tests should **primarily assert that compilation fails**, rather than requiring an exact match on stderr text.

This is an **intentionally non-compiling negative test**, not complete runnable application code. To fix it properly, add:

```java
case Pause pause -> 3;
```

to the `switch` in `MissingCase`. Recompiling will then succeed if no other errors exist.

### Why Are Negative Compile Tests Valuable?

A test that runs `render(new Pause())` can only be written and executed **after the code already compiles**. A negative compile test verifies a different contract: **the compiler must prevent the application from building if the model introduces a new subtype that the selection logic has not added**.

In CI, set up a dedicated compile-negative test or use a compiler testing framework. Do not place intentionally broken fixtures in the same source set built as production code; doing so will keep the entire pipeline red.

## 6. `default` Can Suppress the Missing-Branch Signal

Consider:

```java
static int code(Signal value) {
    return switch (value) {
        case Go go -> 1;
        case Stop stop -> 2;
        default -> -1;
    };
}
```

This is an **illustrative snippet within the scope where `Signal`, `Go`, and `Stop` are declared**. It compiles even without `case Pause`, because `default` covers the remaining non-null values.

If the domain truly requires dedicated handling for `Pause`, `default -> -1` has turned a compiler-detected missing branch into a fallback behavior that may be business-incorrect.

For `sealed` hierarchies with a finite set of variants that each require distinct consideration, prefer **not adding `default` just to silence the error**. Instead, update the logic whenever a subtype is added.

However, `default` is not always wrong. If the business logic **intentionally** groups unlisted variants under a shared behavior, that is a valid design. In that case, tests must explicitly verify the fallback intent, and reviewers must understand that the compiler **no longer forces `switch` updates for every new subtype**.

Nor does `default` **automatically catch `null`**. Thus, "has `default`" is not equivalent to "safe for all reference values."

## 7. Testing `when` Guards and Fallback Branches

A pattern `case T t when condition` only matches when:

1. The type pattern `T t` matches the input.
2. The guard expression `condition` evaluates to `true`.

The compiler **cannot treat an arbitrary guard as always true**. If there is only the branch:

```java
case Approved(var id, var cents) when cents >= 1000 ->
        "large:" + id;
```

then `Approved` values with `cents < 1000` still need a handling path. A `switch` without a case covering the remainder will lack exhaustiveness.

In the complete example, the second branch:

```java
case Approved(var id, var cents) ->
        "approved:" + id + ":" + cents;
```

handles that remainder.

**Required tests:** at least one value that makes the guard true (`1500`), one value that makes the guard false (`500`), and where exact boundaries matter, test `999`/`1000`. If the guard inspects strings, dates/times, state, or arithmetic, also test boundary values and cases that might throw exceptions.

Another negative compile test:

```java
sealed interface Outcome permits Success, Failure {}
record Success(int n) implements Outcome {}
record Failure() implements Outcome {}

static String broken(Outcome value) {
    return switch (value) {
        case Success(var n) when n > 0 -> "positive";
        case Failure f -> "fail";
    };
}
```

This is also **intentionally non-compiling code**: there is no case for `Success` with `n <= 0`. The fix is to add an unguarded `case Success(...)`, or another valid covering mechanism.

**Remember:** having a `case` for a subtype does not automatically mean that subtype is covered if the case is constrained by `when`.

## 8. Testing a `null` Selector Independently of Exhaustiveness

For reference types, `null` is an important runtime case. There are two main policies:

- **Disallow `null`:** define a non-null contract and test API boundaries; a `switch` without `case null` will throw `NullPointerException` if it receives `null`.
- **Allow `null`:** add `case null -> ...` and write tests verifying the business result.

Illustrative example:

```java
static String normalize(Object value) {
    return switch (value) {
        case String text -> text.trim();
        default -> "other";
    };
}
```

`normalize(42)` returns `"other"`, but `normalize(null)` throws **`NullPointerException`**, even though `default` is present.

If you want to handle `null`, write:

```java
static String normalize(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> text.trim();
        default -> "other";
    };
}
```

These two snippets are **illustrative methods inside a class**; they are shown side by side for comparison—do not place two methods with the same name and signature in the same class.

`null` tests must reflect the chosen policy: either expect `NullPointerException` or verify the value returned by `case null`. Never conclude that "exhaustive switch" means "cannot throw NPE."

## 9. Enums: Verifying All Constants and Distinguishing Expressions from Legacy Statements

`enum` is another source of a *closed set*. When a `switch` expression lists all enum constants, the compiler accepts it without `default`.

Save to `EnumExhaustiveDemo.java`:

```java
public class EnumExhaustiveDemo {
    enum Stage { OPEN, CLOSED, HOLD }

    static int score(Stage value) {
        return switch (value) {
            case OPEN -> 10;
            case CLOSED -> 0;
            case HOLD -> 5;
        };
    }

    public static void main(String[] args) {
        for (Stage stage : Stage.values()) {
            System.out.println(stage + "=" + score(stage));
        }
    }
}
```

```bash
javac --release 21 EnumExhaustiveDemo.java
java EnumExhaustiveDemo
```

Stdout:

```text
OPEN=10
CLOSED=0
HOLD=5
```

Iterating over `Stage.values()` is beneficial because it **dynamically retrieves the current list of enum constants**. When a new constant is added, runtime tests can catch unexpected behavior if the code still runs, while the `switch` expression without `default` will also force updating the cases upon **recompilation**.

**Distinguish from legacy statements:** a statement such as:

```java
switch (stage) {
    case OPEN -> System.out.println("opened");
}
```

can compile as a **legacy constant switch statement** even though `CLOSED` and `HOLD` are missing. For strong exhaustiveness guarantees, prefer `switch` expressions or pattern switches that enforce exhaustiveness rules, rather than assuming every statement is checked identically by the compiler.

For an enum `switch` expression without `case null`, a `null` input can still throw `NullPointerException`; `Stage.values()` does not contain `null`, so test separately if the parameter can be nullable.

## 10. Nested Record Patterns: Type-Exhaustive Yet Requiring `null` Data Tests

Record patterns can deconstruct a record's components. However, a nested **record pattern** does not match when the corresponding component is `null`; therefore, with nested record data, you must test the branch that handles missing nested records.

Save to `RecordCoverageDemo.java`:

```java
public class RecordCoverageDemo {
    sealed interface Event permits Success, Failure {}

    record Payload(int amount) {}
    record Success(String id, Payload payload)
            implements Event {}
    record Failure(String reason) implements Event {}

    static String render(Event value) {
        return switch (value) {
            case Success(var id, Payload(var amount)) ->
                    "success:" + id + ":" + amount;

            case Success success ->
                    "missing-payload:" + success.id();

            case Failure(var reason) ->
                    "failure:" + reason;

            case null ->
                    "null-event";
        };
    }

    public static void main(String[] args) {
        System.out.println(render(
                new Success("O", new Payload(7))));
        System.out.println(render(new Success("O", null)));
        System.out.println(render(new Failure("no")));
        System.out.println(render(null));
    }
}
```

```bash
javac --release 21 RecordCoverageDemo.java
java RecordCoverageDemo
```

Stdout:

```text
success:O:7
missing-payload:O
failure:no
null-event
```

Analysis:

- For `Success` with a `Payload`, Java matches the **nested record pattern** and binds `amount`.
- For `Success("O", null)`, the pattern `Payload(var amount)` **does not match `null`**, so Java falls through to the general `case Success success`.
- `case Success success` covers the entire `Success` subtype not handled by earlier cases.
- For `Failure`, matching enters its dedicated branch.
- For `null` at the outer selector, `case null` is selected.

Exhaustiveness at the `Event` level is preserved because both `Success` and `Failure` have unguarded covering branches; however, **the ordering and results of record patterns still require runtime tests**. If tests only construct `Success` with a non-null `Payload`, they will miss the special branch.

A type pattern such as `String s` also does not match a `null` component; a `var` pattern in a component position has different null-matching rules. Do not assume all nested patterns behave identically with `null`.

## 11. `non-sealed` Branches: Root-Level Exhaustiveness Does Not Mean Knowing Every Plugin

`sealed` controls direct subtypes. If a sub-branch is declared `non-sealed`, the hierarchy beneath that branch is open for extension.

Example:

```java
sealed interface Event permits Known, Extension {}
record Known(int code) implements Event {}
non-sealed interface Extension extends Event {}
record Plugin(String key) implements Extension {}
```

A `switch` can be exhaustive by covering the **entire `Extension` branch**:

```java
static String describe(Event value) {
    return switch (value) {
        case Known(var code) -> "known:" + code;
        case Extension extension -> "extension";
    };
}
```

These are **illustrative snippets sharing the same declaration scope**, not standalone programs. Any new plugin directly or indirectly implementing `Extension` is still handled by that general branch.

When testing, choose the contract explicitly:

- If all `Extension` implementations share one handler, test at least one representative implementation and the extension API invariants.
- If each plugin has distinct handling, a root switch with `case Extension e` **does not make the compiler** detect missing logic for a new plugin; separate tests for plugin routing, registry, and versioning are required.

Thus, exhaustiveness only means **every value has a compiler-accepted handling path**, not that every subtype under an open branch is explicitly distinguished.

## 12. Generic Sealed Hierarchies: Testing Against the Actual Selector Type

Exhaustiveness can also depend on the **selector's type arguments** for a generic sealed hierarchy. Conceptually, a sealed interface `Response<T>` might have a specialized subtype that only implements `Response<String>` and another subtype that implements `Response<T>` for any `T`.

With a selector of type `Response<Integer>`, the subtype that only applies to `Response<String>` might **not need** to be covered, because no value of that subtype can simultaneously be compatible with `Response<Integer>` under the type relationships known to the compiler.

Therefore, when writing exhaustive tests for generic sealed types:

1. Compile consumers with the **exact static type of the selector**, rather than changing everything to raw `Response`.
2. Test business-meaningful parameterizations (`Response<String>`, `Response<Integer>`, etc.).
3. Test both patterns with explicit type arguments and patterns whose types are inferred by the compiler.
4. Do not use unchecked casts or raw types to "work around" compile-negative errors; doing so loses static guarantees and can cause runtime failures.

This generic case depends on the JLS *type coverage* rules; do not infer required coverage from subtype names alone while ignoring generic parameterization.

## 13. Binary Evolution: When the Compiler Never Gets to Re-Check

An exhaustive `switch` **is not an invariant guarantee across arbitrary runtime binary combinations**. Suppose:

1. Domain library **v1** declares sealed `Event permits A, B`.
2. A consumer application compiles an exhaustive `switch` with only `A` and `B`.
3. Domain library **v2** adds permitted subtype `C`.
4. The system deploys library v2 **without recompiling** the v1 consumer.
5. If the old consumer encounters an instance of `C`, the previously compiled `switch` can throw **`MatchException`**.

Under Java 21 binary compatibility rules, **adding a permitted direct subtype** is generally *binary compatible*: older binaries do not necessarily fail linkage immediately. However, an old `switch` encountering the new subtype can fail at runtime—this is a **migration compatibility** risk.

Appropriate tests for multi-module/multi-service systems:

- **Source compatibility test:** rebuild the consumer against domain v2; the compiler forces updating missing cases.
- **Binary compatibility test:** run the v1-built consumer against domain/library v2 in an isolated environment; make sure to exercise the path that actually delivers subtype `C`.
- **Integration/contract test:** verify serializers, schemas, message versions, client/server interactions, and rollout procedures when new events are introduced.
- **Telemetry/error handling:** if flows still run old binaries, monitor for `MatchException` and plan appropriate rollbacks or upgrades.

`MatchException` in this scenario is distinct from `NullPointerException` on a null selector. Also avoid adding a catch-all `default` solely to mask version skew if the business logic needs to understand the new subtype.

A similar issue can occur when adding an **enum constant** while an older consumer containing an exhaustive enum switch has not been recompiled. Version testing should reflect real binary combinations, not just clean rebuilds of the latest source.

## 14. Where Should Negative and Positive Tests Live in a Project?

A practical test structure can be divided into layers:

| Test Layer | Input / Action | Expectation |
| --- | --- | --- |
| **Compile-positive** | Build production sources with `--release 21` | All switches requiring exhaustiveness compile |
| **Compile-negative** | Fixture omitting a permitted subtype from a `switch` expression | `javac` fails as expected |
| **Runtime per-case** | Construct each record/enum variant | Correct branch and output |
| **Guard boundary** | Construct values just below, at, and just above `when` thresholds | Selects the right guarded or fallback branch |
| **Null policy** | Pass `null` when the API allows or may receive it | Correct `case null` or defined error |
| **Nested record** | Normal payload and `null` payload | Correct nested pattern or covering branch |
| **Compatibility** | v1 consumer binary receives v2 domain/data | Behavior is identified and acceptable per upgrade plan |

`javac --release 21` is important when the project must target Java 21 even if developer machines run a newer JDK. A test case checked only with preview syntax from another JDK can give misleading conclusions about source compatibility.

If using JUnit, the `check` helper in the example can be replaced with assertions (`assertEquals`, `assertThrows`) and parameterized tests; that is a framework expression choice and **does not alter the compiler's exhaustiveness semantics**. Negative compile fixtures require dedicated tooling to assert that the compiler fails as expected.

## 15. Mutation Testing: Intentionally Breaking a Switch to Verify the Guardrails

A simple review technique is **controlled mutation testing**:

1. Create a test branch or fixture from a compiling example.
2. Delete `case Pending` from a `switch` expression **that has no `default`**.
3. Run `javac --release 21`; the build must fail due to non-exhaustiveness.
4. Restore `case Pending`; the build must succeed.
5. Change the logic in the `Declined` branch to an incorrect result and run runtime tests; the `Declined` test must catch it.
6. Change the guard threshold (`>= 1000` to `> 1000`); the boundary test at `1000` must catch the change if the contract specifies that `1000` enters the large branch.

These mutations verify **two different guardrails**:

- Missing case → blocked by the compiler.
- Case present but wrong logic → blocked by unit tests.

Never leave intentionally broken mutations in a release branch. You can automate negative compilation in a fixture test to ensure compiler checks are not accidentally disabled by broad changes such as adding `default` across consumers.

## 16. Pitfalls When Interpreting Code Coverage

Coverage tools are useful, but their metrics must be read accurately:

- **100% line coverage** does not prove every domain subtype has its own `case`, especially when `default` exists.
- **High branch coverage** does not prove guard boundary values are right if tests did not pick the critical thresholds.
- **Successful compilation** does not prove the return value or side effect of each case is correct.
- **Iterating over all enum constants** does not automatically test `null`, malformed external data, or old binary consumers.
- **Testing all currently known classes** does not prove future implementations of a `non-sealed` branch will be handled properly.

If a domain uses a sealed hierarchy, combining exhaustive switches **without `default` where appropriate** and per-variant tests provides a much stronger change signal than chasing a coverage number alone.

## 17. Common Mistakes and Fixes

| Misconception / Mistake | What Actually Happens | How to Verify or Fix |
| --- | --- | --- |
| "Having `default` makes it exhaustive in a way that reminds me to update every subtype" | `default` masks new subtypes | For closed domains, consider removing `default` and listing cases explicitly |
| "Every `switch` statement must be exhaustive" | Legacy statements using only constants have a compatibility exception | Use an expression or enhanced statement when you want the compiler to catch missing cases |
| "Having a guarded case covers the whole subtype" | A false guard causes the case not to match | Add an unguarded case or proper fallback, and test boundaries |
| "Exhaustive means `null` is handled too" | `null` normally throws `NullPointerException` if no matching case exists | Test the `null` policy separately |
| "Testing one object per record type is enough" | Record patterns can take a different branch when a component is `null` | Test nested data, null components, and guard conditions |
| "Testing `default` for a subtype tests that subtype's business logic" | Fallback logic may violate domain rules | Determine whether the subtype needs its own case and assert the output |
| "The compiler guarantees `MatchException` can never happen" | Old binaries can encounter new subtypes | Recompile and run migration/integration tests |
| "A sealed root guarantees knowing every plugin" | A `non-sealed` branch can be extended indefinitely | Test the extension/registry contract and mapping |
| "Testing all enum constants means external data is handled properly" | Deserialization or schema versions can still fail | Separate domain validation and contract tests |
| "Java `assert` always runs" | Assertions can be disabled without `-ea` | Use framework assertions or throw `AssertionError` explicitly |
| "No need to compile sources with a specific target JDK" | Preview features and different Java versions have different rules/syntax | Use `javac --release 21` for Java 21 lessons |

## 18. Recommended CI Workflow

A pipeline can be structured around what is being verified, not just around tools:

1. **Compile targeting Java 21:** without preview flags, confirm all exhaustive switches in production sources cover every case.
2. **Run consumer unit tests:** one test per subtype and per business-distinct guard branch.
3. **Run compile-negative fixtures:** intentionally add a subtype or omit a case, and verify a non-zero exit code in the compilation fixture.
4. **Run nullable/nested payload tests:** exercise null selectors, null components, and valid boundary values.
5. **Run integration/contract tests:** whenever changing permitted subtypes, enum constants, serialized representations, or shared domain modules.
6. **Review broad `default` branches:** if they suppress compiler reminders for missing cases, decide deliberately whether to keep or remove them.

Example steps for the standalone programs in this lesson:

```bash
javac --release 21 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo

javac --release 21 EnumExhaustiveDemo.java
java EnumExhaustiveDemo

javac --release 21 RecordCoverageDemo.java
java RecordCoverageDemo
```

These three compilation commands should succeed when each program is saved under its **exact filename** with the syntax shown. The negative fixture `MissingCase.java` is run **separately**, and compilation failure is the **expected test outcome**, not an error to fix with `default`.

## 19. Self-Check Exercises

**Exercise 1 — Add a subtype.** In `ExhaustiveSwitchDemo`, add:

```java
record Refunded(String id, long cents)
        implements PaymentResult {}
```

and update the `permits` list. Before editing `render`, try compiling: the compiler should detect the missing case. Then add the `Refunded` case, run a test for a refund, and record the expected output.

**Exercise 2 — Guard.** Change the threshold from `1000` to `2000`, and write tests at `1999`, `2000`, and `2001`. Which result enters the `"large:"` branch? Why are tests with only `500` and `2500` insufficient to protect the boundary condition?

**Exercise 3 — Nested record.** In `RecordCoverageDemo`, remove `case Success success` and try compiling. Then restore that branch, run a test with `new Success("O", null)`, and explain why `Payload(var amount)` does not match.

**Exercise 4 — Enum.** Add the constant `ARCHIVED` to the `Stage` enum; recompile `EnumExhaustiveDemo` and observe the compiler's feedback. Update `score` with explicit handling instead of adding `default` just to skip the new branch.

## 20. Checklist When Reviewing an Exhaustive Switch

Before concluding that testing is sufficient, ask:

- Is the `switch` an **expression**, an **enhanced statement**, or a **legacy statement**?
- What is the selector's static type: enum, sealed hierarchy, generic sealed type, or open interface?
- Is a `default` branch hiding the compiler's ability to report a new subtype?
- Do `when` guards have sufficient unguarded cases or fallback paths for non-matching values?
- Has **every current subtype** and its specific business output been tested?
- Have `null` selectors, nested record components, and guard boundaries been tested?
- For `non-sealed` branches, where is the contract for future subtypes/plugins tested?
- When the domain library changes, are consumers **recompiled**? If old binaries remain, has migration been tested?
- Do negative compile tests genuinely fail due to missing coverage, rather than an unrelated syntax error?
- Do expected-result assertions run independently of runtime configuration?

**Conclusion:** an exhaustive switch is a **compiler-checked coverage guarantee**, especially valuable with `sealed` types and enums. To make that guarantee meaningful in practice, combine **compile-positive, compile-negative, and per-branch runtime tests**, handle `null`/guards/nested records explicitly, and test compatibility as the type hierarchy evolves. None of these test types can completely replace the others.

## Official References

- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [Oracle Java SE 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — §14.11 `switch` Statements](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — §15.28 `switch` Expressions](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification 21 — §13.4 Binary Compatibility and sealed types](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-13.html#jls-13.4)
