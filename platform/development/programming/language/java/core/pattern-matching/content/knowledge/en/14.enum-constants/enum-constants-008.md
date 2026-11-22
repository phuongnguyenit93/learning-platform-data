# Testing the Entire Enum Domain in Java

**Topic:** Java Core Pattern Matching → Enum and Constant  
**Practice version:** Java 21. The rules for `switch` expressions on enums existed prior to Java 21; the program in this lesson uses `case null` with Java 21 `switch` syntax, so compile it with JDK 21 or later.

## 1. What Does “Testing the Entire Enum Domain” Mean?

An `enum` defines a **finite set of named constants**, for example:

```java
enum TaskState {
    NEW, RUNNING, DONE, FAILED
}
```

The *enum domain* of `TaskState` is the set of all valid enum values: `NEW`, `RUNNING`, `DONE`, `FAILED`. The goal of testing the entire domain is not merely to “run a few states,” but to ensure **every existing constant is passed through the logic under test** and **each constant's result is compared against an independent requirement**.

For example, a method that converts a state into a display label could accidentally swap the labels for `DONE` and `FAILED`. If a test only checks that the method returns a non-`null` string, it will miss the bug. A good test must explicitly verify that `DONE` is represented as `SUCCESS` and `FAILED` as `ERROR`.

Three questions should be distinguished:

1. **Domain coverage:** Has every constant of the enum appeared in the test inputs?
2. **Mapping correctness:** Does the output for each constant match the specification?
3. **Maintainability when the enum changes:** When a new constant is added, does the compiler or the test force the developer to update the corresponding behavior?

These three questions complement each other; looping over `values()` only directly addresses the first question.

## 2. `switch` Expressions on Enums and Exhaustiveness

With a selector whose static type is `TaskState`, enum constant labels are written using the constant names without a type prefix:

```java
static String label(TaskState state) {
    return switch (state) {
        case NEW -> "QUEUED";
        case RUNNING -> "IN_PROGRESS";
        case DONE -> "SUCCESS";
        case FAILED -> "ERROR";
    };
}
```

This is an **illustrative method**; it needs to be placed inside a class alongside the `TaskState` declaration. When the compiler knows the enum has exactly the four constants above, the `switch` expression covers all four non-null cases and therefore **does not need `default`**.

If `case FAILED` is omitted while there is still no `default`, the compiler reports a lack of *exhaustiveness*:

```java
// DOES NOT COMPILE when enum has NEW, RUNNING, DONE, FAILED:
return switch (state) {
    case NEW -> "QUEUED";
    case RUNNING -> "IN_PROGRESS";
    case DONE -> "SUCCESS";
    // FAILED has no branch and there is no default.
};
```

The corresponding compiler message in modern JDKs reads something like: `the switch expression does not cover all possible input values`.

**Useful property:** If `CANCELLED` is later added to `TaskState` and the method without `default` is recompiled, the compiler will require handling the new state. This is a **static** layer of checking, though it does not replace unit tests for the returned values.

### When Should You Use `default`?

```java
static String labelWithFallback(TaskState state) {
    return switch (state) {
        case NEW -> "QUEUED";
        case RUNNING -> "IN_PROGRESS";
        default -> "OTHER";
    };
}
```

This example compiles because `default` covers the remaining `DONE` and `FAILED`. However, it also causes two different states to share `OTHER` — which may violate the requirements. If `CANCELLED` is added, the new state would also fall into `default` without the compiler forcing a specific case. Only use `default` when the business logic **genuinely defines** a shared fallback branch.

## 3. Tools for Enumerating and Comparing the Domain

Java provides several useful APIs:

| Tool | Meaning | When to use |
| --- | --- | --- |
| `TaskState.values()` | A new array containing all enum constants in declaration order | Iterate over all states to run tests |
| `EnumSet.allOf(TaskState.class)` | A set containing all constants of the enum | Compare the full domain against the expected table |
| `EnumMap<TaskState, Decision>` | An efficient, clear map keyed by the enum | Store the oracle: the expected result for each state |
| `TaskState.valueOf(name)` | Resolves an exact enum name to its constant | Test conversion from strings or stored data |
| `state.name()` | Exact declared name of the constant | Generate test names, verify round-trip conversion |
| `state.ordinal()` | Declaration position, starting from 0 | Generally **should not** be used as a business identifier |

Example:

```java
for (TaskState state : TaskState.values()) {
    System.out.println(state.name());
}
```

The output is the four names `NEW`, `RUNNING`, `DONE`, `FAILED` in exact declaration order. This loop **guarantees every enum constant has been visited**, but does not prove the logic associated with those constants is correct.

`EnumSet.allOf(TaskState.class)` is not an independent list of expectations: it also derives the domain from the enum itself. Thus, merely comparing `values()` with `EnumSet.allOf()` confirms that the two enumeration mechanisms agree, but **cannot** by itself detect an incorrect mapping.

## 4. Independent Test Oracle: The Most Important Structure

An *oracle* is a source of expected results determined **independently of how the function under test computes its output**. For the state example, write out the requirements table first:

| TaskState | Expected label | Terminal? |
| --- | --- | --- |
| `NEW` | `QUEUED` | `false` |
| `RUNNING` | `IN_PROGRESS` | `false` |
| `DONE` | `SUCCESS` | `true` |
| `FAILED` | `ERROR` | `true` |

A `record Decision(String label, boolean terminal)` lets us verify both the label and the terminal status. The expectation table will be encoded with an `EnumMap` in the complete program.

Condition to check:

```java
EnumSet<TaskState> allStates = EnumSet.allOf(TaskState.class);
EnumMap<TaskState, Decision> expected = new EnumMap<>(TaskState.class);

// expected is explicitly populated from the requirements table, without calling decide().
if (!expected.keySet().equals(allStates)) {
    throw new AssertionError("Bảng kỳ vọng thiếu enum constant");
}
```

The snippet above is **non-standalone illustrative code**: `Decision` and `expected` must be defined and populated; the complete program in section 6 does this.

Checking that the key set equals the entire domain works in two ways: no state is missing, and it avoids relying on an unnecessary hardcoded count of constants. Whenever a new constant is added, the oracle must be updated.

**Note:** If there is already a `switch` expression without `default` and a branch is missing when the enum changes, the compiler blocks the code before tests even run. That is a good thing. If the `switch` has a `default` fallback, a full oracle check still has a chance to catch a new state that has not yet been assigned an expectation.

## 5. Workflow for Testing the Entire Domain

A focused test can follow 5 steps:

1. **Define an independent output contract**, documenting the mapping and any related flags/semantics for each enum constant.
2. **Create an oracle** such as an `EnumMap` or a test data table that explicitly declares every constant.
3. **Verify that the oracle covers the domain** using `EnumSet.allOf()` compared against `expected.keySet()`. Do not just compare sizes: two different sets can still have the same number of elements.
4. **Iterate over `values()`**, invoke the function under test for each value, and compare the full actual result against the expectation. Use an assertion that actually throws an error on mismatch.
5. **Test out-of-domain cases** separately: a `null` selector, invalid name strings, or inputs of other types, depending on the API contract.

For a mapping like `TaskState -> Decision`, consider adding a check for `valueOf(state.name()) == state` if the code has interfaces that store/read enum names. This is a round-trip check of the enum API; it **does not prove business mapping correctness**, so it must not be used as a substitute for an oracle.

### Why Not Just Use `assert`?

Java has the `assert` keyword, but assertions are usually **disabled by default** when running without `-ea`. In a Java SE self-test, use explicit conditions with `throw new AssertionError(...)`, or use a testing library like JUnit 5. When using JUnit, JUnit assertions work regardless of the `-ea` flag.

## 6. Runnable Java 21 Program: Testing All Enum Constants

Create the file **`EnumDomainCoverageDemo.java`**:

```java
public class EnumDomainCoverageDemo {
    enum TaskState { NEW, RUNNING, DONE, FAILED }

    record Decision(String label, boolean terminal) {}

    static Decision decide(TaskState state) {
        return switch (state) {
            case null -> new Decision("NO_STATE", false);
            case NEW -> new Decision("QUEUED", false);
            case RUNNING -> new Decision("IN_PROGRESS", false);
            case DONE -> new Decision("SUCCESS", true);
            case FAILED -> new Decision("ERROR", true);
        };
    }

    static void equal(String label, Object expected, Object actual) {
        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        java.util.EnumMap<TaskState, Decision> expected =
                new java.util.EnumMap<>(TaskState.class);

        // Oracle defined independently of decide().
        expected.put(TaskState.NEW, new Decision("QUEUED", false));
        expected.put(TaskState.RUNNING,
                new Decision("IN_PROGRESS", false));
        expected.put(TaskState.DONE, new Decision("SUCCESS", true));
        expected.put(TaskState.FAILED, new Decision("ERROR", true));

        java.util.EnumSet<TaskState> domain =
                java.util.EnumSet.allOf(TaskState.class);

        equal("expected domain", domain,
                java.util.EnumSet.copyOf(expected.keySet()));

        int checked = 0;
        for (TaskState state : TaskState.values()) {
            Decision actual = decide(state);

            equal(state.name(), expected.get(state), actual);
            equal("valueOf:" + state.name(),
                    state, TaskState.valueOf(state.name()));

            System.out.println(state.name() + "=" + actual.label()
                    + ",terminal=" + actual.terminal());
            checked++;
        }

        equal("count", domain.size(), checked);

        Decision nullResult = decide(null);
        equal("null", new Decision("NO_STATE", false), nullResult);

        System.out.println("null=" + nullResult.label()
                + ",terminal=" + nullResult.terminal());
        System.out.println("COVERED=" + checked);
        System.out.println("ALL_ENUM_CASES_PASSED");
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 EnumDomainCoverageDemo.java
java EnumDomainCoverageDemo
```

**Exact standard output:**

```text
NEW=QUEUED,terminal=false
RUNNING=IN_PROGRESS,terminal=false
DONE=SUCCESS,terminal=true
FAILED=ERROR,terminal=true
null=NO_STATE,terminal=false
COVERED=4
ALL_ENUM_CASES_PASSED
```

### Program Explanation

- `TaskState.values()` produces all four current constants; each constant is passed through `decide(state)`.
- `expected` is an `EnumMap` built from the requirements table. Computing the expected values does not call `decide`, avoiding a test that validates its own buggy logic.
- `EnumSet.allOf(TaskState.class)` is the current domain. `EnumSet.copyOf(expected.keySet())` converts the oracle's keys into an `EnumSet`, then checks **set equality**. Since the current table is non-empty, `copyOf` is valid.
- `Decision` is a record, so the compiler-generated `equals` compares both `label` and `terminal`. If `DONE` returns `SUCCESS` but `terminal=false`, the test still fails.
- `TaskState.valueOf(state.name())` verifies the enum name round-trip for each constant.
- `checked` counts the number of constants actually visited and compares it against the domain size.
- `decide(null)` is tested **outside the loop** because `null` is not an enum constant and is not included in `values()`.
- `ALL_ENUM_CASES_PASSED` is only printed if none of the checks throw `AssertionError`.

In this code, if you change a label in one branch without updating the specification/oracle, the test will report a value mismatch. If you add an enum constant but forget to update the `switch` without `default`, the compiler catches it at compile time. Once you update the `switch` but forget to add it to the oracle, the expected-domain check catches the missing constant.

## 7. `null` Is Not Part of the Enum Domain

`null` can be the value of a **reference variable** declared with an enum type, but `null` **is not a constant defined by the enum**. Therefore:

```java
TaskState state = null;
```

is a valid declaration, yet `state` does not appear in `TaskState.values()` and does not belong to `EnumSet.allOf(TaskState.class)`.

In Java 21, a `null` selector can be handled explicitly with:

```java
case null -> new Decision("NO_STATE", false);
```

**Do not assume `default` catches `null`.** In a Java 21 `switch`, if the selector is null without explicit null handling, the normal result is a `NullPointerException`, even when a standalone `default` is present.

There are two valid policies:

- **Accept null** and return an explicit business result such as `NO_STATE`. In that case, unit tests must cover `decide(null)`.
- **Reject null**, for example by calling `java.util.Objects.requireNonNull(state)` before the `switch` or using `case null -> throw new IllegalArgumentException(...)`. Tests must verify the exact exception type.

Do not increment the enum's “state count” by 1 to count null. It is an additional input test case, not part of the enum domain.

## 8. Testing When Adding, Renaming, or Removing an Enum Constant

Suppose the next version adds `CANCELLED`:

```java
enum TaskState {
    NEW, RUNNING, DONE, FAILED, CANCELLED
}
```

If `decide` still only has the four old `case` branches and **no `default`**, the compiler reports that the `switch` expression is not exhaustive upon recompilation. This is a key benefit of listing all enum constants explicitly.

After adding:

```java
case CANCELLED -> new Decision("CANCELLED", true);
```

the classification code compiles, but the `expected` table in the test still only has four keys. Comparing `expected.keySet()` with `EnumSet.allOf(TaskState.class)` detects that the oracle has not been updated. Once the corresponding expectation is added, the test will also run for `CANCELLED` because `values()` automatically includes the new constant.

Other cases to watch out for:

- **Renaming `DONE` to `COMPLETED`**: branches, stored name-based data, API contracts, and tests must all be updated. `valueOf("DONE")` does not automatically understand the new name.
- **Removing `FAILED`**: the compiler will report errors if code still references the removed constant; the oracle table must also be updated.
- **Reordering constants**: `values()` gets the new declaration order and `ordinal()` changes. Never use `ordinal()` as a persistent storage key or business code.
- **Adding an unconditional `default`**: specific case updates are no longer enforced as the enum evolves; in this situation, an independent domain-oracle check becomes even more important.

**Warning about out-of-sync binaries:** compile-time exhaustiveness does not guarantee that binaries compiled against an older version of an enum can handle a new constant from an updated dependency without recompilation. Multi-module projects should rebuild dependent modules and run tests whenever an enum domain changes.

## 9. Using `@EnumSource` in JUnit 5

In projects using JUnit Jupiter, `@EnumSource` helps run a test once per constant. This is a **separate test example that requires JUnit 5 with the `junit-jupiter-params` module on the test classpath**; it is not part of the Java SE program in section 6.

Create `EnumDomainCoverageTest.java` in the same package as `EnumDomainCoverageDemo`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

class EnumDomainCoverageTest {
    @ParameterizedTest
    @EnumSource(EnumDomainCoverageDemo.TaskState.class)
    void everyConstantHasExpectedDecision(
            EnumDomainCoverageDemo.TaskState state) {

        var expected = Map.of(
            EnumDomainCoverageDemo.TaskState.NEW,
                new EnumDomainCoverageDemo.Decision("QUEUED", false),
            EnumDomainCoverageDemo.TaskState.RUNNING,
                new EnumDomainCoverageDemo.Decision("IN_PROGRESS", false),
            EnumDomainCoverageDemo.TaskState.DONE,
                new EnumDomainCoverageDemo.Decision("SUCCESS", true),
            EnumDomainCoverageDemo.TaskState.FAILED,
                new EnumDomainCoverageDemo.Decision("ERROR", true)
        );

        assertEquals(expected.get(state),
                EnumDomainCoverageDemo.decide(state));
    }

    @Test
    void nullHasItsOwnPolicy() {
        assertEquals(
            new EnumDomainCoverageDemo.Decision("NO_STATE", false),
            EnumDomainCoverageDemo.decide(null)
        );
    }
}
```

`@EnumSource` provides all current constants by default, so when an enum constant is added, the test automatically gets an additional invocation. The expected map is written independently of `decide`; if an expectation has not been added for a new constant yet, `expected.get(state)` returns null and `assertEquals` will fail against the actual `Decision`.

**Limitation:** `@EnumSource` does not supply null by default. Use a separate `@Test` as shown above, or configure an additional source if you want to cover null as well. Do not treat `assertNotNull(decide(state))` as sufficient, as it does not verify business meaning.

### Test Data Should Be Tied to the Specification, Not Copied from the Implementation

If you write expected values using a second `switch` with the same mapping copied from the implementation, both places can share the exact same bug. Whenever possible, use acceptance criteria tables, product requirements, named examples, or agreed-upon input-output samples to build the oracle.

`EnumMap` is well suited for self-tests, while `Map.of` in the JUnit example keeps the table concise. Both must be updated when the enum domain changes.

## 10. Enum Constants and Type Patterns in `switch` Are Two Different Things

In a `switch` whose selector has type **`TaskState`**, you can write:

```java
case NEW -> ...
case RUNNING -> ...
case DONE -> ...
case FAILED -> ...
```

These labels distinguish **specific enum constants**.

If the selector has static type **`Object`**, Java 21 can use a **type pattern** first to match objects belonging to the enum:

```java
static String inspect(Object input) {
    return switch (input) {
        case null -> "NULL";
        case TaskState state -> decide(state).label();
        default -> "NOT_TASK_STATE";
    };
}
```

This is an **illustrative method** placed inside the class containing `TaskState` and `decide`. The `case TaskState state` branch only proves the input is a non-null `TaskState`. It **does not automatically test all four constants**; to distinguish each state, `decide(state)` still needs all cases or an appropriate mapping table.

This connects the **enum and constant** topic with **pattern matching**: a type pattern recognizes a data type, whereas enum constant labels distinguish values within that type. Do not confuse a test that “entered the TaskState case” with “tested the entire domain of TaskState.”

## 11. Extra Cases to Test Outside the Enum Domain

Beyond running all constants, an application may receive external data and convert it to an enum. In that case, also test the **integration boundaries**:

### Converting from Strings

```java
TaskState parsed = TaskState.valueOf("DONE"); // DONE
```

`Enum.valueOf` uses the **exact** declared name and is case-sensitive; `"done"` is invalid without custom normalization. Non-existent names typically throw `IllegalArgumentException`, while a `null` string argument throws `NullPointerException`. This behavior must be tested if the API accepts untrusted string input.

If you want to accept `"done"`, decide on a clear normalization rule such as `toUpperCase(Locale.ROOT)`, and test leading/trailing whitespace as well as invalid cases. Do not assume `name()` or `toString()` will remain a stable long-term API format if enum constants might be renamed.

### Data Persistence

Do not rely on `ordinal()` to encode states in a database or network protocol: adding or reordering enum constants changes ordinals. If persistence is required, use explicit business codes with a compatibility policy and test round-trip conversion for those codes.

### Bidirectional Mapping

When you have both `TaskState -> String` and `String -> TaskState`, test encoding, decoding, and invalid values. Success in one direction does not guarantee the other direction is fully compatible, especially when fallbacks, aliases, or legacy names exist.

## 12. Test Matrix and Coverage Strategy

| Check item | Representative input | Expectation | Assurance type |
| --- | --- | --- | --- |
| Every constant has a mapping | `NEW`, `RUNNING`, `DONE`, `FAILED` | Correct `Decision` per state | Runtime unit test |
| Oracle covers full domain | Expected key set vs. `EnumSet.allOf` | Both sets are equal | Config/specification test |
| Loop misses nothing | `TaskState.values()` | Number of runs equals domain size | Coverage control |
| `null` per contract | `decide(null)` | `NO_STATE` | Out-of-domain unit test |
| Name round-trip | `valueOf(state.name())` | Same constant | Runtime enum API |
| Unknown name | `valueOf("UNKNOWN")` | `IllegalArgumentException` | Invalid input test |
| Added constant with missing case | Add `CANCELLED`, switch not updated | Compile error if no default | Static exhaustiveness |
| Wrong mapping despite full cases | Swap results of `DONE` and `FAILED` | Oracle test detects mismatch | Semantic unit test |
| Using fallback | A constant falls into `default` | Valid only if spec requires it | Review + test |
| `Object`-typed input | `TaskState` and other object types | Correct type pattern/fallback | Integration unit test |

**Do not conflate coverage concepts:** writing an exhaustive `switch` for an enum guarantees completeness **of case selection** at compile time, but it does not prove that branches return the right data, nor does it test the null contract or integration with external inputs.

## 13. Common Mistakes

| Mistake | Why it is insufficient/wrong | How to fix |
| --- | --- | --- |
| Testing only `TaskState.NEW` | Other enum constants are never executed | Iterate `values()` or use `@EnumSource` |
| Looping `values()` and only calling `assertNotNull` | Does not verify whether the mapping is right | Compare each constant against an independent oracle |
| Computing expected values using `decide(state)` itself | The test proves what it is supposed to be checking | Write expectations from the specification |
| Comparing only `expected.size()` against constant count | Two sets of equal size with different members slip through | Compare key sets with `EnumSet.allOf` |
| Omitting `case null` and assuming `default` catches null | Can throw `NullPointerException` | Test null separately and choose an explicit policy |
| Adding `default` just to silence the compiler | Can hide forgotten new constants | Prefer an exhaustive switch without default |
| Relying solely on compile-time exhaustiveness | Does not catch swapped label mappings | Unit test concrete results |
| Using `ordinal()` in persistent data | Values shift when the enum is reordered | Use stable business codes |
| Assuming `@EnumSource` includes `null` | Null is not an enum constant | Write a separate null test |
| Not configuring `junit-jupiter-params` | `@ParameterizedTest`/`@EnumSource` tests fail to run properly | Add the JUnit Jupiter params dependency/config |
| Using `assert` without enabling `-ea` | Self-tests can silently skip checks | Use explicit `AssertionError` or JUnit |
| Forgetting to rebuild dependent modules after enum change | Client code may be out of sync with the new enum | Rebuild and run tests across all related modules |
| Renaming an enum constant without handling old data | `valueOf` cannot resolve the removed name | Use a migration/alias policy and compatibility tests |
| Thinking `case TaskState state` covers testing every constant | Type patterns only distinguish `TaskState` from other types | Add tests for each constant and mapping branch |

## 14. Practice Exercises

1. Create `enum OrderStatus { CREATED, PAID, SHIPPED, DELIVERED, CANCELLED }`. Write a `switch` expression returning a display label for each constant **without default**. Create a separate oracle table and use `values()` to test the entire domain.
2. For `OrderStatus`, also write `isTerminal()` returning `boolean`: `DELIVERED` and `CANCELLED` must be terminal, while other states are not. Test both the label and the terminal flag rather than just one value.
3. Add `RETURNED` to the enum, keep the old `switch` without default, and compile. Note the exhaustiveness error; then add the new case.
4. After fixing the `switch`, intentionally forget to add `RETURNED` to the oracle. Run the key-set check to demonstrate that the domain test detects the missing expectation.
5. Change the `PAID` mapping to `SHIPPED`'s label while keeping all cases present. Observe that the compiler accepts it while the unit test reports a value mismatch.
6. Write a `switch` with `default -> "UNKNOWN"` and compare the pros and cons against the version without default when a constant is added to the enum.
7. Write separate tests for `null`: one where the API accepts null and one where the API actively throws an error. Choose only one policy for production code.
8. Use `@EnumSource(OrderStatus.class)` in JUnit Jupiter to generate test invocations automatically, then compare against independent expectations.
9. Create a parser function that accepts a status name from a request. Test valid names, different casing, empty strings, unknown names, and null; state the policy when a status is renamed.
10. Change the declaration order of the enum, then compare `values()` and `ordinal()`. Explain why business logic tests should rely on constants and stable codes rather than enum positions.
11. Write `switch(Object input)` with `case OrderStatus status`; demonstrate that this branch recognizes the right type but does not automatically replace testing every enum constant.
12. Run `EnumDomainCoverageDemo`, verify all 7 lines of stdout, and intentionally break one expectation to observe `AssertionError` failing the test.

**Lesson achieved when:** you can design tests that run all enum constants, maintain an independent oracle, validate the expected set against the enum domain, understand the effect of an exhaustive `switch` without default, and separately test `null` and out-of-domain inputs.

**References:**

- [Java SE 21 API — `Enum`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html).
- [Java SE 21 API — `EnumSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumSet.html).
- [Java SE 21 API — `EnumMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumMap.html).
- [Java Language Specification 21 — Enum Classes (§8.9)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9).
- [JLS 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [JUnit 5 — Parameterized Tests (`@EnumSource`)](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests-sources-EnumSource).
