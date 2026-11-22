# Testing the null Case in switch with Java Pattern Matching

## 1. Why must `null` be tested separately?

Since Java 21, `switch` officially supports **pattern matching**, **record patterns**, and the **`case null`** label (JEP 441, JEP 440). When handling reference data that may be absent, `null` is a case that requires its own **behavioral contract** and **dedicated tests**—it cannot be inferred merely from the fact that the `switch` compiles or has a `default` branch.

For example:

```java
static String show(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
```

With this code, at least three execution paths are worth testing:

| Selector value | Selected case | Result |
| --- | --- | --- |
| `null` | `case null` | `"missing"` |
| `"hello"` | `case String text` | `"text:hello"` |
| `Integer.valueOf(5)` | `default` | `"other"` |

**The focus of testing** is not merely “running with `null` to see if it crashes,” but specifically asserting that:

1. `null` is handled by **the exact branch designed for it**, or throws the exact expected exception if that is the contract.
2. The `null`-handling branch does not alter the behavior of non-`null` values.
3. `default` and total patterns are not mistaken for “already handling `null`.”
4. With `enum`, `sealed`, `when`, and nested record patterns, **the selector being `null`** is distinguished from **an inner data component being `null`**.
5. Both `switch expression` and `switch statement` can be tested via output, state, or observable side effects.

This article uses **Java 21+** so that `case null`, `case String s when ...`, record patterns, and all tests run without preview flags.

## 2. Java rules to know before writing tests

### 2.1. `case null` handles a `null` selector

For `switch (value)` where `value` is a reference, if `value == null` and the switch block has a matching `case null` label, that label is selected:

```java
String label = switch (value) {
    case null -> "no value";
    case String text -> "text";
    default -> "other";
};
```

This is an illustrative snippet, assuming `value` has type `Object`. `case null` is **not** just shorthand for `default`. It explicitly states that a special reference value must be handled according to its own policy.

### 2.2. Without `case null`, a `switch` on a `null` reference typically throws NPE

```java
static String withoutNull(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
```

Even with `default`, calling `withoutNull(null)` throws **`NullPointerException`**. A good test must **assert that NPE is thrown**, rather than assuming it returns `"other"`. `default` is the fallback branch for **non-`null`** values that do not match the listed cases, not a `catch` or a `null`-catching case.

### 2.3. A total pattern does not mean matching `null`

```java
static String totalPattern(Object value) {
    return switch (value) {
        case Object anything -> "object";
    };
}
```

The pattern `Object anything` can cover all non-`null` objects of the selector type `Object`. That allows the switch to be considered **exhaustive** over the set of values considered, but it does **not** mean `null` will match the `Object` pattern. `totalPattern(null)` still throws `NullPointerException`.

For the same reason, **exhaustive** is not synonymous with **null-safe**. The test suite needs to verify both branch exhaustiveness and the `null`-handling policy.

### 2.4. `case null, default` can be combined when they share the same result

```java
static String fallback(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        case null, default -> "fallback";
    };
}
```

When `null` and all other unmatched values truly share the same behavior, `case null, default` is valid Java 21 syntax. If business logic requires separating “no data” and “unsupported data,” use two separate branches:

```java
case null -> "missing";
default -> "unsupported";
```

The two lines above are illustrative labels inside a complete switch, not a standalone program.

### 2.5. `case null` checks the selector, not every place that can hold null

With `record Order(String id, Notice notice)`, the following two values are very different:

- `switch ((Object) null)`: the **selector** is `null`, so `case null` runs if present.
- `switch (new Order("O2", null))`: the selector is a valid `Order` instance, but the **record's `notice` component is `null`**. The switch's `case null` label is not selected. Other record patterns determine the result.

You should not write a test with only one of the two cases and conclude that the model's `null` risks have been fully tested.

## 3. Designing a contract-based test matrix

When starting to write tests, list the **inputs**, **expected behavior**, **branch that must be selected**, and **test evidence**. For a `switch` using patterns, a baseline matrix includes:

| Case group | Example | What to assert |
| --- | --- | --- |
| Selector `null`, has `case null` | `classify(null)` | Value returned by the null branch |
| Selector `null`, only `default` | `withoutNull(null)` | `NullPointerException` is thrown |
| Selector `null`, total `Object` pattern | `totalPattern(null)` | Still throws `NullPointerException` |
| Selector `null`, has `case null, default` | `fallback(null)` | Shared value per contract |
| Type matches pattern | `"Java"` | `String` branch returns the expected data |
| Type matches but guard fails | `" "` or `Created(null)` | Branch for the remaining condition is selected |
| Value of another type | `Integer`, `Boolean` | Correct fallback branch |
| Enum selector `null` | `stage(null)` | `case null` branch; or NPE if intentionally omitted |
| Sealed selector `null` | `noticeStatus(null)` | Not confused with subtypes |
| Nested record `null` | `new Order("O2", null)` | Outer record still matches, inner pattern may not match |
| `switch statement` receives `null` | `statement(null)` | Expected observable side effect/value |
| Exception in selector expression | `switch (value.toString())` when value is `null` | NPE occurs **before** switch receives the selector |

**Do not merely measure “green coverage”** and assume the `null` contract is protected: branch coverage may record a `default` branch without indicating that it does not handle null. Assertions are more valuable than a test that merely calls a method without verifying anything.

## 4. Complete, standalone scenario: 26 tests with assertions

The program below intentionally has no JUnit dependency. It uses two small helper functions: `equal` compares the expected result and `npe` verifies that a call **must throw `NullPointerException`**. If the behavior is wrong, the program throws `AssertionError` and cannot print the planned total of passing cases.

Save verbatim to the file **`NullSwitchTests.java`**.

```java
import java.util.Objects;
import java.util.function.Supplier;

public class NullSwitchTests {
    enum Stage { NEW, DONE }

    sealed interface Notice permits Created, Cancelled {}
    record Created(String code) implements Notice {}
    record Cancelled(String reason) implements Notice {}
    record Order(String id, Notice notice) {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "selector:null";
            case String text when text.isBlank() -> "text:blank";
            case String text -> "text:" + text;
            case Number number -> "number:" + number.intValue();
            default -> "other";
        };
    }

    static String defaultDoesNotCatchNull(Object value) {
        return switch (value) {
            case String s -> "text:" + s;
            default -> "default";
        };
    }

    static String totalPatternDoesNotCatchNull(Object value) {
        return switch (value) {
            case Object any -> "object";
        };
    }

    static String combinedFallback(Object value) {
        return switch (value) {
            case String s -> "text:" + s;
            case null, default -> "fallback";
        };
    }

    static String stage(Stage stage) {
        return switch (stage) {
            case null -> "stage:null";
            case NEW -> "stage:new";
            case DONE -> "stage:done";
        };
    }

    static String stageWithoutNull(Stage stage) {
        return switch (stage) {
            case NEW -> "new";
            case DONE -> "done";
        };
    }

    static String noticeStatus(Notice notice) {
        return switch (notice) {
            case null -> "notice:null";
            case Created(var code) when code != null && !code.isBlank() ->
                    "created:" + code;
            case Created(var code) -> "created:missing";
            case Cancelled(var reason) -> "cancelled:" + reason;
        };
    }

    static String nested(Object candidate) {
        return switch (candidate) {
            case null -> "order:null";
            case Order(var orderId, Created(var code)) ->
                    "order-created:" + orderId + ":" + code;
            case Order(var orderId, var notice) ->
                    "order-other:" + orderId + ":" +
                    (notice == null ? "null" : notice.getClass().getSimpleName());
            default -> "not-order";
        };
    }

    static String statement(Object value) {
        StringBuilder result = new StringBuilder();
        switch (value) {
            case null -> result.append("statement:null");
            case String s -> result.append("statement:text:").append(s);
            default -> result.append("statement:other");
        }
        return result.toString();
    }

    static int passed = 0;

    static void equal(String name, String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(name + " expected=" + expected
                    + " actual=" + actual);
        }
        passed++;
        System.out.println("PASS " + name + "=" + actual);
    }

    static void npe(String name, Supplier<String> call) {
        try {
            call.get();
            throw new AssertionError(name
                    + " should throw NullPointerException");
        } catch (NullPointerException expected) {
            passed++;
            System.out.println("PASS " + name + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        equal("selector-null", "selector:null", classify(null));
        equal("text-blank", "text:blank", classify(" "));
        equal("text-normal", "text:Java", classify("Java"));
        equal("number", "number:3", classify(3.9));
        equal("other", "other", classify(true));

        npe("default-null", () -> defaultDoesNotCatchNull(null));
        equal("default-object", "default", defaultDoesNotCatchNull(42));
        npe("total-pattern-null", () -> totalPatternDoesNotCatchNull(null));

        equal("combined-null", "fallback", combinedFallback(null));
        equal("combined-object", "fallback", combinedFallback(42));
        equal("combined-string", "text:hello", combinedFallback("hello"));

        equal("enum-null", "stage:null", stage(null));
        equal("enum-done", "stage:done", stage(Stage.DONE));
        npe("enum-without-null", () -> stageWithoutNull(null));

        equal("sealed-null", "notice:null", noticeStatus(null));
        equal("sealed-created", "created:AB", noticeStatus(new Created("AB")));
        equal("sealed-blank", "created:missing", noticeStatus(new Created("")));
        equal("sealed-code-null", "created:missing", noticeStatus(new Created(null)));
        equal("sealed-cancelled", "cancelled:duplicate",
                noticeStatus(new Cancelled("duplicate")));

        equal("nested-selector-null", "order:null", nested(null));
        equal("nested-member-null", "order-other:O2:null",
                nested(new Order("O2", null)));
        equal("nested-created", "order-created:O1:AB",
                nested(new Order("O1", new Created("AB"))));
        equal("nested-cancelled", "order-other:O3:Cancelled",
                nested(new Order("O3", new Cancelled("x"))));

        equal("statement-null", "statement:null", statement(null));
        equal("statement-string", "statement:text:hi", statement("hi"));
        equal("statement-other", "statement:other", statement(7));

        System.out.println("TOTAL=" + passed);
    }
}
```

Compile and run:

```bash
javac --release 21 -encoding UTF-8 NullSwitchTests.java
java NullSwitchTests
```

**Exact output when all 26 cases pass:**

```text
PASS selector-null=selector:null
PASS text-blank=text:blank
PASS text-normal=text:Java
PASS number=number:3
PASS other=other
PASS default-null=NullPointerException
PASS default-object=default
PASS total-pattern-null=NullPointerException
PASS combined-null=fallback
PASS combined-object=fallback
PASS combined-string=text:hello
PASS enum-null=stage:null
PASS enum-done=stage:done
PASS enum-without-null=NullPointerException
PASS sealed-null=notice:null
PASS sealed-created=created:AB
PASS sealed-blank=created:missing
PASS sealed-code-null=created:missing
PASS sealed-cancelled=cancelled:duplicate
PASS nested-selector-null=order:null
PASS nested-member-null=order-other:O2:null
PASS nested-created=order-created:O1:AB
PASS nested-cancelled=order-other:O3:Cancelled
PASS statement-null=statement:null
PASS statement-string=statement:text:hi
PASS statement-other=statement:other
TOTAL=26
```

The example uses ASCII output strings to avoid terminal encoding differences. The code requires no libraries outside the JDK. The `record` and `sealed interface` types live in the same class so it can be compiled as a single file.

**Important for test runners:** the total `TOTAL=26` is only printed when all `equal` and `npe` calls have completed normally. If a case fails to return the expected value or fails to throw the expected exception, `AssertionError` causes the program to fail at that case; partial stdout must not be interpreted as a full PASS result.

## 5. Analyzing null selector cases and guard cases

### 5.1. Do not confuse `null` with an empty/blank string

`classify` has the branches:

```java
case null -> "selector:null";
case String text when text.isBlank() -> "text:blank";
case String text -> "text:" + text;
```

With `null`, **`case null` runs**; no `text` variable is bound and `text.isBlank()` is not called. Therefore, this is a test case for **null selector**, not a test case for `String.isBlank()`.

With `" "`, the selector is a non-null `String`; the guard `text.isBlank()` returns `true` and the result is `"text:blank"`. With `"Java"`, the guard returns `false`, Java proceeds to the unguarded `String` pattern and returns `"text:Java"`.

If tests only use `null` and `"Java"`, a logic bug in the blank-string branch may be missed. Conversely, testing only a blank string does not prove `case null` works correctly.

### 5.2. Why also test Number and Boolean?

In `classify(3.9)`, `Double` is a `Number`. The code returns `"number:3"` because `Number.intValue()` of 3.9 returns 3. Testing helps catch accidental reordering of cases or changes to the conversion expression.

`classify(true)` returns `"other"` via `default` because `Boolean` matches neither `String` nor `Number`. This serves as a control against `null`: **an unrecognized value** goes to `default`, whereas **having no value** goes to `case null`.

### 5.3. Why test a failing guard?

With `noticeStatus(new Created(null))`, the selector is **not null**: it is a `Created` record, but its `code` component is `null`. The record pattern `Created(var code)` can bind `code == null`. The guard:

```java
when code != null && !code.isBlank()
```

returns `false` when `code` is `null`; thanks to short-circuit `&&`, `code.isBlank()` is not called, so no NPE is thrown. The subsequent unguarded `case Created(var code)` branch handles it with `"created:missing"`.

The test suite verifies both `new Created("")` and `new Created(null)` to prove that the guard logic properly identifies both forms of missing code. Testing `noticeStatus(null)` is **a completely different scenario**, which must return `"notice:null"`.

## 6. `default` does not catch null: test exceptions proactively

This is one of the most valuable checks when maintaining a switch:

```java
static String defaultDoesNotCatchNull(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        default -> "default";
    };
}
```

**Test the exact contract if null must currently be rejected:**

```java
npe("default-null", () -> defaultDoesNotCatchNull(null));
```

And include a non-String, non-null control value:

```java
equal("default-object", "default", defaultDoesNotCatchNull(42));
```

If only the second case is tested, the test has not proven at all that `default` does not catch `null`.

### Do not swallow exceptions in tests

An anti-pattern:

```java
// WRONG: merely calling the function and catching generically without asserting anything.
try {
    defaultDoesNotCatchNull(null);
} catch (Exception ignored) {
    // Unknown exception type, yet still treated as test passed.
}
```

In the program's `npe(...)` helper, if no NPE occurs, the code **throws AssertionError**. If the method throws a different exception, that exception is not caught as a PASS. Only when it is specifically `NullPointerException` is the `passed` counter incremented.

When using JUnit 5, the equivalent expression is `assertThrows(NullPointerException.class, () -> method(null))`; the JUnit style will be illustrated in a later section.

## 7. Enum: exhaustiveness does not automatically handle null

Suppose:

```java
enum Stage { NEW, DONE }
```

A switch expression **that already lists all enum constants** can compile even without `case null`:

```java
static String stageWithoutNull(Stage stage) {
    return switch (stage) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

However, calling `stageWithoutNull(null)` still throws `NullPointerException`. This is confirmed by the `enum-without-null` case in the example.

If the contract allows `null`:

```java
static String stage(Stage stage) {
    return switch (stage) {
        case null -> "stage:null";
        case NEW -> "stage:new";
        case DONE -> "stage:done";
    };
}
```

Two **independent properties** must be tested: `stage(null)` returns `"stage:null"` and `stage(Stage.DONE)` still returns `"stage:done"`.

You should not add `default` just to “avoid NPE”: it does not handle `null` in the way people commonly assume, and it can hide compiler warnings when the enum is extended with a new constant. If the policy forbids `null`, keep the NPE (or use an explicit input check); if the policy allows it, write `case null`.

## 8. Sealed hierarchy: null selector differs from null component

A sealed interface with two records:

```java
sealed interface Notice permits Created, Cancelled {}
record Created(String code) implements Notice {}
record Cancelled(String reason) implements Notice {}
```

You can write an exhaustive switch expression with the two subtypes:

```java
static String noticeStatus(Notice notice) {
    return switch (notice) {
        case null -> "notice:null";
        case Created(var code) when code != null && !code.isBlank() ->
                "created:" + code;
        case Created(var code) -> "created:missing";
        case Cancelled(var reason) -> "cancelled:" + reason;
    };
}
```

Cases to include:
- `noticeStatus(null)` returns `"notice:null"`: null selector.
- `noticeStatus(new Created("AB"))` returns `"created:AB"`: guard succeeds.
- `noticeStatus(new Created(""))` returns `"created:missing"`: guard fails because empty.
- `noticeStatus(new Created(null))` returns `"created:missing"`: null component while the record exists.
- `noticeStatus(new Cancelled("duplicate"))` returns `"cancelled:duplicate"`: other subtype still works.

With a `sealed` hierarchy, listing the subtypes ensures coverage of valid instances according to the type structure. `case null` adds a policy for an absent value, **without replacing any subtype case**.

## 9. Nested record patterns: two levels of null require two tests

Structure:

```java
record Order(String id, Notice notice) {}
```

and switch:

```java
static String nested(Object candidate) {
    return switch (candidate) {
        case null -> "order:null";
        case Order(var orderId, Created(var code)) ->
                "order-created:" + orderId + ":" + code;
        case Order(var orderId, var notice) ->
                "order-other:" + orderId + ":" +
                (notice == null ? "null" : notice.getClass().getSimpleName());
        default -> "not-order";
    };
}
```

Key differences:

| Input | Result | Reason |
| --- | --- | --- |
| `null` | `"order:null"` | Null selector, selects `case null` |
| `new Order("O2", null)` | `"order-other:O2:null"` | Selector is `Order`; pattern `Created(...)` does not match the null component; pattern `var notice` receives null |
| `new Order("O1", new Created("AB"))` | `"order-created:O1:AB"` | Both `Order` and nested record `Created` match |
| `new Order("O3", new Cancelled("x"))` | `"order-other:O3:Cancelled"` | Nested record is not `Created`, uses the general `Order` case |

**A testing rule:** with nested record patterns, distinguish null at **the selector itself** from null at **each significant component**. Do not assume that having `case null` handles every inner accessor/data stage.

In Java 21, `var` at a reference component can bind a `null` value, whereas a nested record pattern `Created(...)` does not match a null component. If a record's accessor is custom-written and throws an exception when accessed, that is a different error scenario, not simply a null case. When an accessor throws an error during matching, a `MatchException` with a cause may occur; this must be tested separately according to the accessor's contract.

## 10. Switch statement: test actions, not just values

Not every switch returns a value. With a `switch statement`, you may need to verify logs, events, state updates, or service calls in the null branch.

The runnable example in `NullSwitchTests.java` uses `StringBuilder` as observable state:

```java
static String statement(Object value) {
    StringBuilder result = new StringBuilder();
    switch (value) {
        case null -> result.append("statement:null");
        case String s -> result.append("statement:text:").append(s);
        default -> result.append("statement:other");
    }
    return result.toString();
}
```

Three cases:
- `statement(null)`: `"statement:null"`.
- `statement("hi")`: `"statement:text:hi"`.
- `statement(7)`: `"statement:other"`.

Even though the sample method returns a string for convenient testing, the internal construct is still a **switch statement**. In a real application, replace `StringBuilder` with an event sink, mock service, or state observed after execution.

A good test for side effects must ensure:
1. When the selector is `null`, the exact action of the null case is executed.
2. No action from other branches runs unexpectedly.
3. When the value is non-null, existing actions remain preserved.
4. If the null branch must return/stop early, no subsequent step is executed.

**An enhanced switch statement** using patterns in Java 21 has exhaustiveness rules; it should not be confused with a traditional statement on `int` or `String` using constant cases that may not be exhaustive.

## 11. Testing `case null, default`: convenient, but must match intent

The test suite uses:

```java
static String combinedFallback(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null, default -> "fallback";
    };
}
```

Three assertions protect its meaning:

```java
equal("combined-null", "fallback", combinedFallback(null));
equal("combined-object", "fallback", combinedFallback(42));
equal("combined-string", "text:hello", combinedFallback("hello"));
```

If `case null, default` is replaced with `default`, the **combined-null** test fails (NPE). If replaced with `case null` without keeping a branch covering other types, the switch expression lacks exhaustiveness for `Object`. If the `String` result is accidentally changed, the **combined-string** test catches it.

Only use the combined label when null and values outside the listed cases are **truly equivalent in business logic**. If null needs a different message, do not combine them just to shorten the code. Policy correctness matters more than fewer lines.

## 12. Distinguishing NPE before switch from NPE due to a null selector

There are cases that look like a “null bug in switch” where `case null` cannot help. For example:

```java
Object value = null;

String result = switch (value.toString()) {
    case null -> "null string";
    default -> "other";
};
```

This is **an example that intentionally throws `NullPointerException`**, not a program meant to run in normal flow. Actual sequence:

1. Java needs to **evaluate the selector expression `value.toString()`**.
2. Because `value == null`, the `toString()` call throws `NullPointerException` immediately.
3. The switch **never receives the selector result**, so `case null` has no chance to be selected.

A proper policy must handle null before dereferencing:

```java
String result = switch (value) {
    case null -> "null object";
    default -> value.toString();
};
```

The second snippet takes `value` directly as the selector and handles `null` before calling any method. This illustrates **the timing of the error**, not an automatic rule to replace every method call with a switch.

Similarly, when code auto-unboxes an `Integer` that is `null` to produce an `int` before the switch, NPE can occur during the unboxing step. With an `Integer` selector in Java 21, `case null` can be checked directly without unboxing beforehand.

## 13. Using JUnit 5 to protect behavior in a project

In a project with JUnit 5, there is no need to write `equal` and `npe` yourself like in the standalone program. You can write tests with `assertEquals`, `assertThrows`, or `assertAll`.

This example **is an illustrative test class snippet, not a standalone zero-dependency runnable file**. You need JUnit 5 on the test classpath and access to the methods/types under `NullSwitchTests`:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class NullSwitchJUnitTest {
    @Test
    void nullSelectorMustTakeNullCase() {
        assertEquals("selector:null", NullSwitchTests.classify(null));
    }

    @Test
    void defaultDoesNotConsumeNull() {
        assertThrows(NullPointerException.class,
                () -> NullSwitchTests.defaultDoesNotCatchNull(null));
    }

    @Test
    void nullComponentIsNotNullSelector() {
        assertEquals("order-other:O2:null",
                NullSwitchTests.nested(new NullSwitchTests.Order("O2", null)));
    }

    @Test
    void guardDistinguishesMissingCode() {
        assertAll(
                () -> assertEquals("notice:null",
                        NullSwitchTests.noticeStatus(null)),
                () -> assertEquals("created:missing",
                        NullSwitchTests.noticeStatus(new NullSwitchTests.Created(null))),
                () -> assertEquals("created:AB",
                        NullSwitchTests.noticeStatus(new NullSwitchTests.Created("AB")))
        );
    }
}
```

With the structure of `NullSwitchTests.java` above, member types and methods have package-private access; a test class in the same package (here, the default package) can call them. In a real project, place classes in proper packages or adjust visibility appropriately—do not make production logic public just for tests.

### Avoiding false positives when testing exceptions

An anti-pattern:

```java
@Test
void weakTest() {
    try {
        NullSwitchTests.defaultDoesNotCatchNull(null);
    } catch (Exception ignored) {
        // Does not verify whether it is NPE or another exception.
    }
}
```

Such a test can be “green” even if no error occurred, or if the wrong type of error occurred. `assertThrows(NullPointerException.class, ...)` explicitly requires the exception type; if the method returns normally or throws a different exception, the test fails.

If the contract changes from “throw NPE” to “return a null-specific value,” you must **update the test and business rationale** rather than simply deleting the assertion so CI turns green without protecting behavior.

## 14. How to measure test coverage more accurately

The 26-case suite in the sample program is one set of cases, **not a guarantee that every switch in the system is sufficiently tested**. In production code, you should also apply:

1. **Branch coverage:** confirm that every required branch—including `case null`, guard true/false, `default`, and subtypes—has a test that triggers it.
2. **Exception assertions:** if an API intentionally rejects null, assert the exact NPE (or defined exception), rather than merely seeing that the test runs.
3. **Mutation-oriented reasoning:** suppose you delete `case null`; which test catches the change? If no test fails, protection is insufficient.
4. **Boundary and domain coverage:** `""`, `" "`, null component code, null nested record, new enum constants, wrong-type cases.
5. **Side-effect verification:** for statements, assert the invocation count and data sent to services, not just the return value.
6. **Parameterized tests:** group similar inputs into a table when there are many types/values, but keep the null case explicit instead of hiding it inside a huge dataset.
7. **Regression after refactor:** when converting an `if` chain to `switch` or changing `default`, run all null and non-null cases to confirm before/after behavior.
8. **Runtime/compiler compatibility:** run tests with the same language level as the deployed application; the pattern switch and record patterns syntax in this article require Java 21.

Do not measure quality solely by test count. Two tests with precise assertions for `null`/non-null are worth more than dozens of tests that cannot observe which branch ran.

## 15. Common mistakes when testing the null case

### 15.1. Assuming having `default` is enough

Wrong under Java 21 semantics: `default` does not automatically handle a null selector. You must use `case null` or explicitly expect NPE.

### 15.2. Testing only null and forgetting other cases

Adding `case null` can accidentally alter `case String` or `default`. Always include non-null controls to preserve existing behavior.

### 15.3. Testing only a null component and declaring the null selector safe

`new Order("O2", null)` is a **non-null Order**. It does not test `case null` on that same switch.

### 15.4. Catching generic `Exception` and letting the test pass

This hides wrong-type errors and errors from other operations. Assert the exact exception required by the contract.

### 15.5. Confusing a guard with a null case

With `case String s when s.isBlank()`, a null selector does not enter that guard. Blank string and null tests must be separate.

### 15.6. Relying on exhaustiveness without testing null

An enum/sealed switch can be exhaustive for instances of the type yet still throw NPE for `null` if there is no corresponding case. The compiler does not replace a null-contract test.

### 15.7. Ignoring side effects of a switch statement

A test that merely calls `void process(null)` without asserting logs, events, or state can stay green even when the wrong branch executes. Use a mock/spy or an observable sink.

### 15.8. Equating a selector exception with an exception during matching

`switch (obj.toString())` when `obj == null` throws an error before the switch block selects a case. `case null` has no chance to handle it; to test and fix properly, analyze where dereferencing occurs.

### 15.9. Ignoring null in sealed/record subtype cases

`new Created(null)` is still a `Created`. If a guard uses `code.isBlank()` without checking `code != null`, it can throw NPE. Testing `Created(null)` and `notice == null` are two distinct cases.

### 15.10. Using `List.of(null)` to build fixtures without noticing pre-switch failure

`List.of(...)` does not accept null elements, so `List.of((Object) null)` throws NPE when creating the list, before the method under test is even called. To test a null selector, pass `null` directly to the method or use a fixture that intentionally allows null.

### 15.11. Looking only at stdout without assertions

Printing `"OK"` does not prove the right case was selected if the test does not compare against an expected value. The sample program uses `AssertionError`; in a real project, use a testing framework.

## 16. Practice exercises and answers

**Exercise 1 — Default and null.** Given:

```java
String result = switch (value) {
    case String s -> "text";
    default -> "other";
};
```

With `Object value = null`, does it return `"other"` or throw an error?

**Answer:** throws `NullPointerException`. `default` does not automatically catch a null selector.

**Exercise 2 — Exhaustive enum.** `enum Stage { NEW, DONE }` already has `case NEW` and `case DONE`. Without `case null`, what happens with `stageWithoutNull(null)`?

**Answer:** the switch expression still compiles because all enum values are covered; calling it with null still throws NPE.

**Exercise 3 — Two levels of null.** Do `nested(null)` and `nested(new Order("O2", null))` produce the same result?

**Answer:** no. The first returns `order:null`; the second returns `order-other:O2:null` according to the example. The selector and the record component are two different positions.

**Exercise 4 — Guard of Created.** Does `noticeStatus(new Created(null))` enter `case null`?

**Answer:** no. The selector is a `Created` object. The guarded case's condition returns false, and the unguarded `Created` branch handles it with `created:missing`.

**Exercise 5 — Combining branches.** When is `case null, default -> "fallback"` appropriate?

**Answer:** only when the business contract truly treats null and the remaining unmatched values as the same kind of fallback. If you want to return `missing` for null and `unsupported` for other types, split the branches.

**Exercise 6 — Asserting NPE.** Why should you use `assertThrows` instead of `try/catch (Exception ignored)` in unit tests?

**Answer:** `assertThrows` verifies that an exception **must occur and be of the exact expected type**. Catching and ignoring allows the test to pass even when the function throws nothing or throws an unexpected error type.

**Exercise 7 — Null before switch.** For `switch (value.toString())` with `value == null`, does adding `case null` fix it?

**Answer:** no. `value.toString()` throws NPE before the switch receives the selector. You need to check for null before dereferencing or use `switch (value)` directly with `case null`.

**Exercise 8 — Regression testing.** When adding `case null` to a switch statement with side effects, what should be tested besides the output for null?

**Answer:** the action of the null branch, confirmation that other branches do not run, important side effects and ordering, plus at least the previously supported non-null values.

**Exercise 9 — Object pattern.** With `switch(Object value) { case Object any -> "object"; }`, why must `value == null` still be tested?

**Answer:** the `Object` pattern can be a pattern covering all non-null instances, but it does not match null. The null case still throws NPE.

**Exercise 10 — Measuring test effectiveness.** If `case null` is removed from `classify`, which test in `NullSwitchTests` fails?

**Answer:** the `selector-null` test: instead of returning `"selector:null"`, the call will throw NPE. This is a straightforward check of how sensitive the test suite is to null bugs.

## 17. Key takeaways and short checklist

- Before writing tests, clearly decide **the null selector contract**: dedicated branch, combined fallback, or rejection via exception.
- **`case null`** is the way to handle a null selector in a switch on a reference type; **`default`** does not implicitly substitute for it.
- **Exhaustiveness does not automatically mean null safety**; enums, sealed hierarchies, or `Object` patterns still require considering a null selector.
- **`case null, default`** is valid, but should only be used when both situations truly share the same meaning.
- **A null record component differs from a null selector**; for nested record patterns, add test cases for each significant data level.
- **A `when` guard** is not a null branch. Test guard-true, guard-false, and null separately.
- For a **switch expression**, assert the return value or exception; for a **switch statement**, assert behavior/side effects.
- **NPE before case selection** (dereferencing or unboxing in the selector) is not caught by `case null`.
- A good test suite includes **positive, negative, boundary, and regression cases**, not just running once and glancing at the output.
- Run tests with Java 21+ to match the semantics of pattern matching for switch and record patterns in this article.

**Official documentation:**
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [Java Language Specification 21 — The switch Statement (`14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — Switch Expressions (`15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
