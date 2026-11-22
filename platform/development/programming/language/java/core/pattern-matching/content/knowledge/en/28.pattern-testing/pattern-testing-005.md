# Testing Each Subtype of a Sealed Hierarchy in Java 21

## 1. Why Does a Sealed Hierarchy Still Need Testing?

A `sealed class` or `sealed interface` allows Java to restrict which types are permitted to extend or implement it. This is especially useful when combined with **pattern matching for `switch`**: the compiler can rely on the closed hierarchy structure to check whether a `switch expression` or enhanced `switch statement` is **exhaustive**.

However, **exhaustive does not mean the logic is correct**:

- The compiler can prove that every subtype is covered by some `case`, but it does not know what the business result should be.
- A single subtype can have **multiple `when` branches**, each of which needs boundary-value testing.
- A record's constructor may contain **validation** and must be tested separately.
- `case null`, null record components, or invalid data have their own behavior that cannot be inferred from `permits` alone.
- When adding a subtype or changing the hierarchy, we need to protect both **compilability** and the **runtime test suite**.

Therefore, the goal of this lesson is to build a **test matrix for each leaf subtype (*leaf subtype*)**, checking main branches, guards, boundary values, invariants, null handling, and the `permits` structure. The lesson also shows a mechanism to detect when a new subtype is introduced that the test suite has not yet updated for.

**Version:** `sealed` has been a standard feature since Java 17 (JEP 409). Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) have been standard features since **Java 21**. The complete program in this lesson uses **JDK 21 or later**, with the command `javac --release 21`, without needing `--enable-preview`.

After this lesson, you will be able to:
1. Distinguish **direct subtypes** from **leaf subtypes** in a multi-level hierarchy.
2. Design tests for each variant and each guard branch of a `switch`.
3. Use data-driven table tests, exception tests, and reflection tests via `getPermittedSubclasses()`.
4. Know exactly what the compiler guarantees, and what still must be tested.
5. Maintain tests when subtypes are added, removed, renamed, or moved to another branch.

## 2. Domain Example: A Two-Level Sealed Hierarchy Tree

Suppose the system receives commands:

```text
Command (sealed interface)
├── OrderCommand (sealed interface)
│   ├── Submit(id, items)     (record)
│   └── Cancel(id)            (record)
└── SystemCommand (sealed interface)
    ├── Retry(job, attempt)   (record)
    └── Abort(job, code)      (record)
```

The types are declared as follows:

```java
// Illustrative declarations; the complete program is in section 5.
sealed interface Command permits OrderCommand, SystemCommand {}

sealed interface OrderCommand extends Command
        permits Submit, Cancel {}

sealed interface SystemCommand extends Command
        permits Retry, Abort {}

record Submit(String id, int items) implements OrderCommand {}
record Cancel(String id) implements OrderCommand {}
record Retry(String job, int attempt) implements SystemCommand {}
record Abort(String job, int code) implements SystemCommand {}
```

Distinguish two testing levels:

- **Major branch level:** `Command` directly permits `OrderCommand` and `SystemCommand`. If a method classifies by parent branch, you need to test a representative from both groups.
- **Leaf level:** `Submit`, `Cancel`, `Retry`, and `Abort` are `final` records. When a `switch` deconstructs each subtype, you must test **every leaf type**, not just one `OrderCommand` and one `SystemCommand`.

The root's `permits` lists **direct subtypes**, and does not automatically list all leaf records at deeper levels. Therefore, a test that only queries `Command.class.getPermittedSubclasses()` will see the two intermediate interfaces; to verify all four leaves, you must continue inspecting the intermediate branches or traverse recursively.

### Two Pattern Styles in the Same Domain

A parent-branch classification operation can use **type patterns**:

```java
static String group(Command command) {
    return switch (command) {
        case OrderCommand ignored -> "ORDER";
        case SystemCommand ignored -> "SYSTEM";
        case null -> "NONE";
    };
}
```

Meanwhile, a detailed processing operation uses **record patterns**:

```java
// Illustrative cases inside a switch expression.
case Submit(String id, int items) when items == 0 ->
    "SUBMIT_EMPTY:" + id;
case Submit(String id, int items) ->
    "SUBMIT:" + id + ":" + items;
```

From a testing perspective, the two methods have different needs: `group` needs to test the **parent groups**, whereas `describe` needs to test **each leaf type and guard condition**.

## 3. Separating Three Layers of Assurance: Compiler, Runtime Tests, and Structural Tests

### 3.1. The Compiler Checks the Type Hierarchy and Exhaustiveness

With a closed sealed hierarchy, a `switch` that has matching cases for all leaves can be evaluated by the compiler as exhaustive. If a leaf subtype is added and its corresponding case is missing, `javac` will report an error upon recompilation.

This is a **type-level** check, not proof that every output or every business branch is correct.

### 3.2. Runtime Tests Verify Data and Results

Tests need to confirm:
- Which subtype does a given input belong to?
- Is the output of the corresponding case correct?
- Is the guard true or false at the threshold?
- Does the constructor reject invalid states?
- Is a null selector handled according to the contract?

The compiler does not know that `Retry(job, 3)` must be labeled `RETRY_ESCALATE` or that `Abort(job, 500)` must be `ABORT_CRITICAL`: these are business rules protected by tests.

### 3.3. Reflection Tests Protect the Expected Subtype List

The `Class::isSealed` and `Class::getPermittedSubclasses` APIs help inspect the hierarchy directly at runtime. Tests can compare the set of permitted `Class` objects against the expected set of `Class` objects.

Benefits:
- Immediately notice when a subtype is added or moved to another branch while the test has not updated its list.
- Verify that intermediate types remain `sealed` as designed.
- Independent of whether a separate `switch` accidentally uses `default` and masks the new branch.

**Limitation:** Reflection tests do not prove that each guard has been tested; the subtype list and test cases must be designed to complement each other.

## 4. Designing the Test Matrix Before Coding

For a handler returning strings, build a test table as follows:

| Leaf subtype/input | Branch to test | Expected output |
| --- | --- | --- |
| `Submit("O1", 0)` | Guard `items == 0` | `SUBMIT_EMPTY:O1` |
| `Submit("O2", 2)` | Normal `Submit` case | `SUBMIT:O2:2` |
| `Cancel("O3")` | `Cancel` case | `CANCEL:O3` |
| `Retry("J1", 2)` | Before `attempt >= 3` threshold | `RETRY:J1:2` |
| `Retry("J1", 3)` | Right at guard threshold | `RETRY_ESCALATE:J1` |
| `Abort("J2", 499)` | Before `code >= 500` threshold | `ABORT:J2:499` |
| `Abort("J2", 500)` | Right at guard threshold | `ABORT_CRITICAL:J2` |
| `null` | `case null` | `NULL` |

The table shows that **one test per subtype is not necessarily enough**: `Submit` has empty and non-empty branches; `Retry` and `Abort` have guard thresholds. You need at least one test for each expected outcome, and tests on both sides of the boundary.

**Do not only test "nice" examples:** For `attempt >= 3`, a test with `attempt = 10` only proves that very large values are handled, while a bug using `> 3` instead of `>= 3` could slip through. The `2/3` pair directly catches boundary bugs. For error codes `>= 500`, the `499/500` pair works the same way.

The minimum matrix also needs groups beyond the happy path:
- `null` on the `Command` selector.
- Empty/blank/null IDs; negative item counts; negative attempt counts if disallowed by the constructor.
- Parent branches `OrderCommand` and `SystemCommand`.
- The set of direct subtypes according to `permits` at each sealed node.
- When adding a new leaf: the compiler, reflection tests, and runtime tests must all be updated.

## 5. Complete Java 21 Program: 17 Tests

This lesson uses a small test harness from Java SE, **without requiring JUnit**. Each passing test prints `PASS ...`; if the result differs from expected, the code throws `AssertionError`, preventing the program from completing normally. This approach makes it quick to run in a single file and gives reliable results even without enabling the `-ea` flag.

Create the file **`SealedSubtypeTestsDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class SealedSubtypeTestsDemo {
    sealed interface Command permits OrderCommand, SystemCommand {}
    sealed interface OrderCommand extends Command permits Submit, Cancel {}
    sealed interface SystemCommand extends Command permits Retry, Abort {}

    static void requireId(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("blank id");
        }
    }

    record Submit(String id, int items) implements OrderCommand {
        Submit {
            requireId(id);
            if (items < 0) {
                throw new IllegalArgumentException("negative items");
            }
        }
    }

    record Cancel(String id) implements OrderCommand {
        Cancel {
            requireId(id);
        }
    }

    record Retry(String job, int attempt) implements SystemCommand {
        Retry {
            requireId(job);
            if (attempt < 0) {
                throw new IllegalArgumentException("negative attempt");
            }
        }
    }

    record Abort(String job, int code) implements SystemCommand {
        Abort {
            requireId(job);
        }
    }

    static String describe(Command command) {
        return switch (command) {
            case Submit(String id, int items) when items == 0 ->
                "SUBMIT_EMPTY:" + id;

            case Submit(String id, int items) ->
                "SUBMIT:" + id + ":" + items;

            case Cancel(String id) ->
                "CANCEL:" + id;

            case Retry(String job, int attempt) when attempt >= 3 ->
                "RETRY_ESCALATE:" + job;

            case Retry(String job, int attempt) ->
                "RETRY:" + job + ":" + attempt;

            case Abort(String job, int code) when code >= 500 ->
                "ABORT_CRITICAL:" + job;

            case Abort(String job, int code) ->
                "ABORT:" + job + ":" + code;

            case null -> "NULL";
        };
    }

    static String group(Command command) {
        return switch (command) {
            case OrderCommand ignored -> "ORDER";
            case SystemCommand ignored -> "SYSTEM";
            case null -> "NONE";
        };
    }

    static int tests = 0;

    static void expect(String name, String expected, String actual) {
        tests++;
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    static void expectIllegalArgument(String name, Runnable action) {
        tests++;
        try {
            action.run();
        } catch (IllegalArgumentException ex) {
            System.out.println("PASS " + name);
            return;
        }
        throw new AssertionError(
            name + ": expected IllegalArgumentException");
    }

    static void expectPermits(
            String name, Class<?> type, Set<Class<?>> expected) {
        tests++;
        if (!type.isSealed()) {
            throw new AssertionError(name + ": type must be sealed");
        }

        Set<Class<?>> actual =
            new HashSet<>(Arrays.asList(type.getPermittedSubclasses()));

        if (!expected.equals(actual)) {
            throw new AssertionError(
                name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        expectPermits("root-permits", Command.class,
            Set.of(OrderCommand.class, SystemCommand.class));
        expectPermits("order-permits", OrderCommand.class,
            Set.of(Submit.class, Cancel.class));
        expectPermits("system-permits", SystemCommand.class,
            Set.of(Retry.class, Abort.class));

        expect("submit-empty", "SUBMIT_EMPTY:O1",
            describe(new Submit("O1", 0)));
        expect("submit-positive", "SUBMIT:O2:2",
            describe(new Submit("O2", 2)));
        expect("cancel", "CANCEL:O3",
            describe(new Cancel("O3")));
        expect("retry-before-boundary", "RETRY:J1:2",
            describe(new Retry("J1", 2)));
        expect("retry-at-boundary", "RETRY_ESCALATE:J1",
            describe(new Retry("J1", 3)));
        expect("abort-before-boundary", "ABORT:J2:499",
            describe(new Abort("J2", 499)));
        expect("abort-at-boundary", "ABORT_CRITICAL:J2",
            describe(new Abort("J2", 500)));

        expect("group-order", "ORDER", group(new Cancel("O4")));
        expect("group-system", "SYSTEM", group(new Retry("J3", 1)));
        expect("null-describe", "NULL", describe(null));
        expect("null-group", "NONE", group(null));

        expectIllegalArgument("invalid-id",
            () -> new Submit(" ", 1));
        expectIllegalArgument("invalid-items",
            () -> new Submit("O5", -1));
        expectIllegalArgument("invalid-attempt",
            () -> new Retry("J4", -1));

        System.out.println("TOTAL=" + tests);
    }
}
```

Compile and run from the directory containing the file using **JDK 21 or later**:

```bash
javac --release 21 SealedSubtypeTestsDemo.java
java SealedSubtypeTestsDemo
```

Exact stdout output:

```text
PASS root-permits
PASS order-permits
PASS system-permits
PASS submit-empty
PASS submit-positive
PASS cancel
PASS retry-before-boundary
PASS retry-at-boundary
PASS abort-before-boundary
PASS abort-at-boundary
PASS group-order
PASS group-system
PASS null-describe
PASS null-group
PASS invalid-id
PASS invalid-items
PASS invalid-attempt
TOTAL=17
```

This program is both a complete example and a small test suite. It uses `Objects.equals` to compare outputs, catches the exact `IllegalArgumentException` when validation is expected to fail, and uses reflection to verify the exact permitted branches in the hierarchy. It has no dependencies outside Java SE.

## 6. Explaining the Test Groups

### 6.1. Checking `permits` at All Three Sealed Nodes

`expectPermits("root-permits", Command.class, ...)` protects the direct structure of `Command`. The next two calls protect the direct structures of `OrderCommand` and `SystemCommand`.

Inside the helper:

```java
if (!type.isSealed()) {
    throw new AssertionError(name + ": type must be sealed");
}
Set<Class<?>> actual =
    new HashSet<>(Arrays.asList(type.getPermittedSubclasses()));
```

`getPermittedSubclasses()` only returns **the direct permitted subtypes**, not a recursive list of all leaves. Using a `Set` instead of comparing array order lets you test the set of types without accidentally depending on declaration order.

Comparing `expected.equals(actual)` checks the **exact** permitted set, not just the count. If `Cancel` is replaced by another subtype while the total remains two, the test still detects the difference.

**Strategy limitation:** This test intentionally requires updating when the hierarchy design changes. A new subtype is not necessarily a bug; a failure here reminds the development team to review handlers and add tests. You should not automatically "fix" it by using the reflection result itself as the expected value, because then the check can no longer detect changes.

### 6.2. Testing Each Leaf Subtype

In the example there are four leaf types:

- `Submit`: two tests for `items == 0` and `items > 0`.
- `Cancel`: one test for the standalone branch.
- `Retry`: two tests for before and at the `attempt >= 3` threshold.
- `Abort`: two tests for before and at the `code >= 500` threshold.

This is different from only testing `group(new Submit(...))` and `group(new Retry(...))`: the latter only proves the two **parent branches**, and does not prove that `Cancel` or `Abort` is described correctly.

### 6.3. Testing Parent Type Patterns

`group` uses `case OrderCommand ignored` and `case SystemCommand ignored`. The two tests `group-order` and `group-system` test one representative for each major branch; `null-group` tests `case null`.

For a function that only classifies parent branches, two representative tests may suffice for the method's own logic. However, if you want to guarantee that **every leaf subtype** is routed correctly, add `group` tests with all of `Submit`, `Cancel`, `Retry`, and `Abort`. Deciding the coverage level depends on the method's contract: do not confuse parent-level coverage with leaf-level coverage.

### 6.4. Testing Invalid Inputs

The records have constructors that check:
- IDs must not be null/empty/blank.
- `Submit.items` must not be negative.
- `Retry.attempt` must not be negative.

`expectIllegalArgument` invokes a `Runnable` and requires **the exact type** `IllegalArgumentException`. If the code does not throw an exception, the helper throws `AssertionError`. If it throws a different type, the test also fails because the helper only catches `IllegalArgumentException`.

This is how you test the **domain invariants** of each subtype. An exhaustive hierarchy does not by itself guarantee that a record's data is valid.

### 6.5. Testing Null on the Selector

`describe(null)` and `group(null)` have two separate tests. Both methods have `case null`, returning `NULL` and `NONE` respectively.

Do not assume `default` catches a null selector. If a pattern switch needs to allow null, design `case null` explicitly or check at the boundary. If the contract forbids null, use validation such as `Objects.requireNonNull` and test the corresponding exception.

## 7. Exhaustiveness Does Not Replace Testing Each `when` Branch

Consider two consecutive cases:

```java
case Retry(String job, int attempt) when attempt >= 3 ->
    "RETRY_ESCALATE:" + job;
case Retry(String job, int attempt) ->
    "RETRY:" + job + ":" + attempt;
```

The compiler sees the **unguarded** `Retry` case at the end and can therefore conclude that all valid `Retry` instances are covered. However, it does not prove that the condition `attempt >= 3` reflects the business requirement accurately.

Therefore, tests must check at least:
- **Just before the threshold:** `attempt = 2`.
- **Right at the threshold:** `attempt = 3`.
- **Past the threshold:** you can add `attempt = 4` to increase confidence.
- **Invalid data:** if negative values are forbidden, test `attempt = -1` directly at the constructor.

Similarly, `Abort` has the threshold `code >= 500`; `499` and `500` are the boundary pair to prioritize. If real logic uses multiple error-code ranges, split them into corresponding `when` branches.

**Principle:** Testing should not only follow the number of subtypes; it must follow the **meaningful paths** inside each subtype. Counting one test per class while ignoring guards, validation, and fallbacks creates a false sense of coverage.

## 8. When Adding a Subtype: Compiler and Tests Must Work Together

Suppose we add a `Pause` type under `SystemCommand`:

```java
// Illustrative snippet of changing the hierarchy; do not add standalone
// to the file in section 5 without updating all related places.
sealed interface SystemCommand extends Command
        permits Retry, Abort, Pause {}

record Pause(String job) implements SystemCommand {}
```

Consequences to consider:

1. `SystemCommand` must directly permit `Pause` via `permits`.
2. `group` still has `case SystemCommand ignored`, so it can handle `Pause` at the parent-branch level without needing a separate case.
3. `describe` only has cases for `Submit`, `Cancel`, `Retry`, and `Abort`, so the compiler will report that **the switch expression is not exhaustive** after adding the new leaf and recompiling.
4. The `system-permits` test currently expects the set `Retry`/`Abort`; once `Pause` is added, the test will fail until the expected set is updated.
5. The development team must add a test `describe(new Pause(...))` and any related guards/invariants; merely adding a case so the code compiles does not guarantee the behavior is tested properly.

This is a useful workflow: **compile failure prompts updating handlers**, while **reflection tests prompt updating the test matrix and reviewing the hierarchy**.

### Should You Add `default` Just to Make the Build Pass?

If the goal is to handle every variant of a sealed hierarchy explicitly, do not rush to add:

```java
// Illustrates a fallback that can mask omissions:
default -> "OTHER";
```

A broad `default` can keep a switch exhaustive when a new subtype appears, preventing the compiler from reminding you where specific logic is needed. However, `default` is a valid choice if the contract genuinely specifies that all remaining subtypes must be handled the same way. Base the decision on requirements, not on avoiding diagnostics.

### Testing Changes Across Modules

In a multi-module system, if subtypes and consumers are built/deployed separately, you must test against **the compatible set of artifacts**. An old switch compiled against a previous hierarchy can fail at runtime with an incompatible change (in some circumstances a `MatchException` may occur). CI should compile and run consumer tests against the actual deployed dependency versions, not just the source of an isolated module.

## 9. How to Measure Coverage Without Misinterpreting It

**Line coverage** measures how many lines were executed; **branch coverage** measures control-flow branches; however, no single number means "the entire domain has been tested."

For a sealed hierarchy, you need to examine at least four layers:

| Coverage layer | Question | How to prove |
| --- | --- | --- |
| **Type coverage** | Does every leaf subtype have a test? | List of leaves/test cases and `permits` checks |
| **Pattern-case coverage** | Is every required case executed? | Output tests for each record pattern and guard |
| **Boundary coverage** | Are guards tested on both sides? | Pairs `2/3`, `499/500`, `0` |
| **Invariant/negative coverage** | Is invalid data rejected properly? | Constructor, exception, null, and boundary-input tests |

Tools like JaCoCo can measure line/branch coverage, but a coverage report does not replace a **subtype matrix**. For example, a `Retry(100)` test may execute the escalate case without proving the boundary at 3 is right. Similarly, executing every line in `group` does not prove all leaf subtypes have their own correct behavior.

**Mutation testing** can add value: if changing `>= 3` to `> 3` still leaves all tests green, the test suite is missing boundary values. If removing the `Cancel` case already causes the compiler to report non-exhaustive, that is a compile-time check, and you do not need a runtime test to prove a syntax/compilation error.

## 10. Extending to JUnit and Parameterized Tests

For a real codebase, you can move the cases from section 5 to **JUnit 5 (Jupiter)**; however, JUnit is an external dependency outside the JDK, so the snippets below are **test-framework illustrations**, not a standalone program. You need to declare the Jupiter dependency and configure Maven/Gradle/test runner appropriately in your project.

A data-driven table test can use `@ParameterizedTest` and `@MethodSource`:

```java
// Illustration inside a test class that has imported JUnit Jupiter.
// Does not compile standalone without the dependency and domain types.
static java.util.stream.Stream<org.junit.jupiter.params.provider.Arguments>
describeCases() {
    return java.util.stream.Stream.of(
        org.junit.jupiter.params.provider.Arguments.of(
            new Submit("O1", 0), "SUBMIT_EMPTY:O1"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Submit("O2", 2), "SUBMIT:O2:2"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Cancel("O3"), "CANCEL:O3"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Retry("J1", 2), "RETRY:J1:2"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Retry("J1", 3), "RETRY_ESCALATE:J1"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Abort("J2", 499), "ABORT:J2:499"),
        org.junit.jupiter.params.provider.Arguments.of(
            new Abort("J2", 500), "ABORT_CRITICAL:J2")
    );
}

@org.junit.jupiter.params.ParameterizedTest
@org.junit.jupiter.params.provider.MethodSource("describeCases")
void describeAllCases(Command input, String expected) {
    org.junit.jupiter.api.Assertions.assertEquals(
        expected, describe(input));
}
```

Depending on project structure, the types nested inside `SealedSubtypeTestsDemo` must be imported via the enclosing name or moved to top-level types; the example above **assumes the types and `describe` are already in the test's scope**.

Benefits of table-driven tests:
- Easy to see which subtypes/guards already have test data.
- Easy to add many input variants.
- Test framework names clearly display which case failed.
- Data cases can be separated for parsers, mappings, formatters, and domain services.

Do not lose the `permits` and invariant tests when migrating to a framework. Parameterization is only a **way to organize test cases**, and does not create coverage on its own.

## 11. Nulls, Nested Record Patterns, and `non-sealed`: Edge Cases

### 11.1. Selector Null and Component Null Are Different

`case null` handles **the selector itself**. If a record contains a nested record component, a null component can cause a nested record pattern **not to match**, even when the outer record is non-null. For example:

```java
// Illustrative only, independent of Command in section 5.
record Location(String city) {}
record UserEvent(Location location) {}

// event has type Object:
boolean matched =
    event instanceof UserEvent(Location(String city));
```

If `event` is `new UserEvent(null)`, then the nested `Location(...)` does not match; `matched` evaluates to `false`. With a sealed hierarchy, a switch deemed exhaustive by the compiler based on type structure can still encounter a `MatchException` at runtime if a nested null prevents any case from matching.

For data that must be non-null, check the invariant in the constructor. If null is valid, create a dedicated case and test for it—for example, a component pattern `var location` with a guard `when location == null`, placed before specific nested patterns.

### 11.2. `non-sealed` Opens the Variant Set

A direct subtype of a sealed type can be `non-sealed` to allow other classes to extend it. In that case, the set of leaf classes is no longer closed: `getPermittedSubclasses()` on the root only tells you the direct permitted branches, and **does not** list every subtype that might exist beneath the `non-sealed` branch.

Appropriate testing approach:
- Test the official implementations owned by the project.
- Include tests for **unknown/third-party implementations** if the contract allows extension.
- If a switch needs to be exhaustive, use a type pattern covering the entire open branch or an intentional fallback.
- Do not claim to test "every subtype in the world" via reflection on the root if the hierarchy has an open branch.

### 11.3. A Record Does Not Automatically Mean Valid Data

Records automatically generate constructors, accessors, `equals`, `hashCode`, and `toString`, but **do not automatically check business invariants**. If a component has a reference type, it can be null unless rejected by the constructor. If a component holds a mutable object, a record does not perform a deep copy automatically.

The test suite for each subtype should be based on the **actual contract**, rather than assuming every record is deeply immutable or non-null.

## 12. Testing Workflow in Projects and CI

A practical checklist:

1. **List the hierarchy:** Diagram sealed, final, and non-sealed nodes. Separate direct subtypes from leaf subtypes.
2. **Define each operation's contract:** Which methods process by parent branch, and which read leaf data and guards?
3. **Build the test matrix:** At least one case per leaf, plus cases for every guard and boundary value.
4. **Add invariant tests:** Record/class constructors must handle invalid data according to specification.
5. **Add null tests:** Selector null and component null are two distinct scenarios.
6. **Protect the hierarchy:** Test `getPermittedSubclasses()` at each key sealed node; compare against the exact expected subtype set.
7. **Compile all consumers:** Let the compiler check exhaustive `switch` statements/expressions when new subtypes are added.
8. **Run runtime tests and measure coverage:** Do not use coverage % as a substitute for the business matrix.
9. **Review API changes:** When the hierarchy changes, update compile-time handlers, runtime fixtures, data mappers, serialization, and corresponding tests.
10. **Test actual build/deploy artifacts:** Especially when modules are released independently.

Example minimal CI commands for the standalone file:

```bash
javac --release 21 -Xlint:all SealedSubtypeTestsDemo.java
java SealedSubtypeTestsDemo
```

The checks throw `AssertionError`, so **`java -ea` is not required**. If a comparison or hierarchy check fails, the program throws `AssertionError`, allowing the CI job to detect test failure when the process exits abnormally. With JUnit, use the project's official runner/CI integration.

## 13. Common Mistakes

| Mistake | Why it is insufficient | How to fix |
| --- | --- | --- |
| Testing only one object per parent branch | May miss sibling leaves | List every leaf and create separate tests |
| Only one happy path per leaf | Misses guards and boundaries | Test thresholds and unguarded branches |
| Believing sealed + exhaustive switch means business logic is right | Compiler only guarantees type coverage | Assert expected outputs, exceptions, and invariants |
| Checking only `Command.getPermittedSubclasses()` | Only sees the two direct interfaces | Also check intermediate sealed nodes |
| Comparing only the count of subtypes | One subtype could be swapped without changing the count | Compare the exact expected `Class` set |
| Using a broad `default` to silence compiler errors | New subtypes are not forced to have dedicated handling | Only use a fallback when the contract requires it |
| Forgetting `case null` or null components | Can throw NPE/`MatchException` | Define a null policy and test it explicitly |
| Testing exceptions with an overly broad `catch (Exception)` | Unexpected errors also make the test pass | Catch/assert the exact exception class |
| Using Java `assert` without enabling `-ea` | Assertions may not execute | Use JUnit assertions or a helper that throws `AssertionError` |
| Relying solely on coverage % | Boundary tests may still be missing | Use a subtype × guard × invariant matrix |
| Adding a subtype without updating test fixtures | Test suite no longer reflects the new domain | Review `permits`, handlers, and all consumers |

## 14. Practice Exercises

**Exercise 1 — Add tests for values just past the threshold.** Add `Retry("J1", 4)` and `Abort("J2", 501)`. Which bugs do the `2/3` and `499/500` pairs already catch, and how do these two tests add confidence?

**Exercise 2 — Extend with a new subtype.** Add `record Pause(String job) implements SystemCommand` and update `permits`. Observe the compile error in `describe`, update `expectPermits("system-permits", ...)`, and add a test for `Pause`. Compare with `group` — why does the parent-branch classification method not need to change?

**Exercise 3 — New guarded record variant.** Add a new condition for `Submit` such as `items >= 100`, returning `SUBMIT_BULK:<id>`. Place the new guarded case in the proper order so it is not dominated. Write tests at `99` and `100`, and verify that the `items == 0` case still works correctly.

**Exercise 4 — Null inside a nested record.** Create a sealed hierarchy for `UserEvent` with a record containing `Location`. Intentionally allow or forbid `location == null`; design tests to verify both the nested record pattern case and the null fallback.

**Exercise 5 — Try mutation testing.** Temporarily change `attempt >= 3` to `attempt > 3`; re-run the test suite and note which case fails. Then restore the code and try changing `code >= 500` to `code > 500`.

## 15. Conclusion

Testing a **sealed hierarchy** does not stop at getting the compiler to accept an exhaustive `switch`. You must test **every leaf subtype**, **guards and boundaries**, **invariants**, **null handling**, and the `permits` structure at key sealed nodes.

A strong strategy combines **compile-time exhaustiveness**, **reflection tests protecting the subtype set**, and **runtime tests with clear expected outputs**. When new types are added, these three layers help catch missing handlers, missing tests, and incorrect business logic—rather than merely knowing that the code still compiles.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- Java SE 21 API — `Class.getPermittedSubclasses()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
