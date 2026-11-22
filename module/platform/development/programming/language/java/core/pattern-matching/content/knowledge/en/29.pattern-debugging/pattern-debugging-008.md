# Using Small Tests to Isolate Faulty Patterns in Java Pattern Matching

## 1. Goal: Turn a “Wrong Pattern” into a Reproducible Case

When encountering a bug related to an `instanceof` pattern, record pattern, or `switch` with patterns in Java, the visible result is often just “wrong branch selected”, “case not entered”, “throws NullPointerException”, or “fails to compile”. Those are **symptoms**, not the root cause yet.

Instead of reading a long business-processing method and guessing, create **small, deterministic tests** that check each stage in turn:

```text
Input value
      |
      v
Does the selector expression evaluate successfully?
      |
      v
Does the object have the right pattern type?
      |
      v
Do the outer record and nested records match?
      |
      v
Did the accessor return a valid component or throw an error?
      |
      v
Is the when/&& condition correct?
      |
      v
Which case is selected? What result does the case body produce?
```

Core idea: **each test only needs to answer one question**, using the smallest possible data for that question. After finding the faulty step, keep a **regression test** so the next fix does not reintroduce the bug.

In this article, “isolate” means:

- Reducing the problem to one or a few records, one method with a pattern, and a few clear inputs.
- Comparing **expected** (behavior per requirements) with **actual** (actual program behavior).
- Separating checks for **type**, **record shape**, **guard**, **null**, and **case body behavior**.
- Changing only one hypothesis at a time, without simultaneously renaming types, reordering branches, and rewriting the entire switch.

The examples use **Java 21+** because record patterns and pattern matching for switch are standard features in Java 21 (JEP 440, JEP 441). For simple `instanceof` type patterns, the feature has been standard since Java 16.

## 2. A Concrete Bug: A Whitespace-Only Address Gets Accepted

Consider two records:

```java
record Address(String city) {}
record Shipment(String shipmentId, Address destination) {}
```

Business requirements:

- A shipping address whose city contains meaningful characters returns a label of the form `ship:Da Nang`, after trimming leading and trailing whitespace.
- If `destination` is `null`, or `city` is `null`, or `city` is all whitespace, return `destination:missing`.
- If the selector is `null`, return `input:missing`.
- If the selector is not a `Shipment`, return `unsupported`.

Here is the **intentionally buggy** version:

```java
static String buggy(Object candidate) {
    return switch (candidate) {
        case null -> "input:missing";
        case Shipment(var shipmentId, Address(var destinationCity))
                when destinationCity != null ->
                "ship:" + destinationCity.strip();
        case Shipment(var shipmentId, var destination) ->
                "destination:missing";
        default -> "unsupported";
    };
}
```

The snippet above is an illustrative method; it needs to be placed inside a class where the records are declared. The problematic line is **`when destinationCity != null`**. That condition lets the string `"   "` pass through because it is **not `null`**. After `strip()`, the label becomes `"ship:"` even though the business requirement expects `"destination:missing"`.

It is not that the record pattern failed to match. The record pattern **matched properly**, but the guard was too permissive.

### A Truly Runnable Minimal Reproducer (MRE)

Save as `TinyGuardRepro.java`:

```java
public class TinyGuardRepro {
    record Address(String city) {}
    record Shipment(Address destination) {}

    static String classify(Object candidate) {
        return switch (candidate) {
            case Shipment(Address(var city)) when city != null ->
                    "ship:" + city.strip();
            case Shipment(var destination) -> "destination:missing";
            case null -> "input:missing";
            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Shipment(new Address("   "))));
    }
}
```

Run:

```bash
javac --release 21 -encoding UTF-8 TinyGuardRepro.java
java TinyGuardRepro
```

Actual output:

```text
ship:
```

Expected per business requirements: `destination:missing`.

This is a **bug reproducer**, not a claim that it already returns the right result. It has stripped away frameworks, databases, APIs, logging, and unrelated parts. If the minimal version still reproduces `ship:`, we can investigate the pattern and guard in isolation.

## 3. Technique: Splitting the Bug into Three Tiny Tests

To avoid guessing the cause, split the same object `new Shipment("S-2", new Address("   "))` into independent checks.

### Step A — Check the Outer Type

```java
static String typeOnly(Object candidate) {
    return candidate instanceof Shipment shipment
            ? "type:Shipment" : "type:other";
}
```

With a `Shipment` whose city is all whitespace, the result is `type:Shipment`. That means the object **has the right type**; the bug is not in the outer type check.

### Step B — Check the Record Pattern Without Applying the Guard

```java
static String shapeOnly(Object candidate) {
    if (candidate instanceof Shipment(
            var shipmentId, Address(var destinationCity))) {
        return "shape:" + shipmentId + ":" + destinationCity;
    }
    return "shape:miss";
}
```

With the same input, the result is `shape:S-2:   ` (after the final colon there are **three spaces**). Both the outer record pattern and the inner `Address(...)` pattern matched; the variable `destinationCity` holds the exact whitespace string.

### Step C — Check the Exact Business Condition

```java
static String guardOnly(Object candidate) {
    if (candidate instanceof Shipment(
            var shipmentId, Address(var destinationCity))
            && destinationCity != null && !destinationCity.isBlank()) {
        return "guard:pass";
    }
    return "guard:fail";
}
```

With a three-space string, `isBlank()` is `true`, so `!isBlank()` is `false` and the result is `guard:fail`. At this point there is enough evidence that the bug is not in the type or record shape, but in the **guard missing a non-empty/non-blank check**.

Fix in the switch:

```java
case Shipment(var shipmentId, Address(var destinationCity))
        when destinationCity != null && !destinationCity.isBlank() ->
        "ship:" + destinationCity.strip();
```

This line is **one `case` label** inside the switch, not a standalone statement. Keep the `Shipment(var shipmentId, var destination)` case after it to handle invalid addresses.

## 4. Small Data Matrix: Each Row Guards One Hypothesis

For the bug above, you do not need huge production data. A few objects constructed in memory are enough.

| Input | Expected Branch | Reason |
| --- | --- | --- |
| `new Shipment("S-1", new Address(" Da Nang "))` | `ship:Da Nang` | Valid city, leading/trailing whitespace stripped |
| `new Shipment("S-2", new Address("   "))` | `destination:missing` | Whitespace-only string |
| `new Shipment("S-3", null)` | `destination:missing` | Entire address record is missing |
| `new Shipment("S-4", new Address(null))` | `destination:missing` | Address record exists, city component is null |
| `null` | `input:missing` | Null selector |
| `Integer.valueOf(17)` | `unsupported` | Unsupported outer type |

Each input exposes **one semantic distinction**:

- `new Shipment("S-3", null)` tests whether the nested record pattern `Address(...)` matches null.
- `new Shipment("S-4", new Address(null))` tests whether the `var destinationCity` pattern can receive a null value from `Address`'s accessor.
- `new Shipment("S-2", new Address("   "))` tests the difference between “non-null” and “has meaningful content”.
- `null` tests the null policy of the **selector**, not a null component.
- `17` tests `default` to ensure fixing the guard does not accidentally alter behavior for other types.

**Tip:** only add another input when it helps distinguish a remaining suspected cause. If two inputs expose the exact same condition, you can keep the second one in the regression suite without necessarily putting both in the minimal reproducer.

## 5. Complete Java 21 Example: Isolate, Reproduce, and Verify the Fix

Save the following program verbatim to **`IsolatePatternBugDemo.java`**. The small test suite uses `AssertionError` to fail clearly when expected differs from actual, without needing JUnit or other frameworks.

In `reproduceBug`, we **intentionally expect to see a difference** to prove the buggy code still reproduces the issue. This checks a known bug, not a claim that `buggy(...)` is correct. Only `fixed(...)` must satisfy expected.

```java
public class IsolatePatternBugDemo {
    record Address(String city) {}
    record Shipment(String shipmentId, Address destination) {}

    record Fragile(String value) {
        public String value() {
            if (value == null) {
                throw new IllegalStateException("accessor failed");
            }
            return value;
        }
    }

    // Bug: city != null still allows whitespace-only strings.
    static String buggy(Object candidate) {
        return switch (candidate) {
            case null -> "input:missing";
            case Shipment(var shipmentId, Address(var destinationCity))
                    when destinationCity != null ->
                    "ship:" + destinationCity.strip();
            case Shipment(var shipmentId, var destination) ->
                    "destination:missing";
            default -> "unsupported";
        };
    }

    // Fix: add !isBlank() condition, keep the remaining cases.
    static String fixed(Object candidate) {
        return switch (candidate) {
            case null -> "input:missing";
            case Shipment(var shipmentId, Address(var destinationCity))
                    when destinationCity != null && !destinationCity.isBlank() ->
                    "ship:" + destinationCity.strip();
            case Shipment(var shipmentId, var destination) ->
                    "destination:missing";
            default -> "unsupported";
        };
    }

    // Step 1: check only the outer type.
    static String typeOnly(Object candidate) {
        return candidate instanceof Shipment shipment
                ? "type:Shipment" : "type:other";
    }

    // Step 2: deconstruct the record without business validation.
    static String shapeOnly(Object candidate) {
        if (candidate instanceof Shipment(
                var shipmentId, Address(var destinationCity))) {
            return "shape:" + shipmentId + ":" + destinationCity;
        }
        return "shape:miss";
    }

    // Step 3: check the guard separately.
    static String guardOnly(Object candidate) {
        if (candidate instanceof Shipment(
                var shipmentId, Address(var destinationCity))
                && destinationCity != null && !destinationCity.isBlank()) {
            return "guard:pass";
        }
        return "guard:fail";
    }

    // Accessor intentionally throws an exception, helping distinguish matching errors.
    static String fragilePattern(Object candidate) {
        if (candidate instanceof Fragile(var value)) {
            return "fragile:" + value;
        }
        return "not-fragile";
    }

    // No null case: default does not automatically catch a null selector.
    static String noNullCase(Object candidate) {
        return switch (candidate) {
            case Shipment(var shipmentId, var destination) -> "shipment";
            default -> "other";
        };
    }

    static int passed;

    static void assertEqual(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected=" + expected
                    + " actual=" + actual);
        }
        passed++;
        System.out.println("PASS " + label + "=" + actual);
    }

    static void reproduceBug(String expected, String actual) {
        if (expected.equals(actual)) {
            throw new AssertionError("bug not reproduced");
        }
        System.out.println("REPRO blank expected=" + expected
                + " actual=" + actual);
    }

    public static void main(String[] args) {
        Shipment valid = new Shipment(
                "S-1", new Address(" Da Nang "));
        Shipment blank = new Shipment(
                "S-2", new Address("   "));
        Shipment missing = new Shipment("S-3", null);
        Shipment nullCity = new Shipment(
                "S-4", new Address(null));

        assertEqual("type-blank", "type:Shipment", typeOnly(blank));
        assertEqual("shape-blank", "shape:S-2:   ", shapeOnly(blank));
        assertEqual("guard-blank", "guard:fail", guardOnly(blank));
        reproduceBug("destination:missing", buggy(blank));

        assertEqual("fixed-valid", "ship:Da Nang", fixed(valid));
        assertEqual("fixed-blank", "destination:missing", fixed(blank));
        assertEqual("fixed-missing", "destination:missing", fixed(missing));
        assertEqual("fixed-null-city", "destination:missing", fixed(nullCity));
        assertEqual("fixed-null-selector", "input:missing", fixed(null));
        assertEqual("fixed-other", "unsupported", fixed(17));

        assertEqual("shape-null-destination", "shape:miss",
                shapeOnly(missing));
        assertEqual("shape-null-city", "shape:S-4:null",
                shapeOnly(nullCity));
        assertEqual("guard-valid", "guard:pass", guardOnly(valid));

        try {
            noNullCase(null);
            throw new AssertionError("NullPointerException expected");
        } catch (NullPointerException expected) {
            assertEqual("missing-case-null", "NullPointerException",
                    expected.getClass().getSimpleName());
        }

        try {
            fragilePattern(new Fragile(null));
            throw new AssertionError("MatchException expected");
        } catch (MatchException expected) {
            assertEqual("accessor-cause", "IllegalStateException",
                    expected.getCause().getClass().getSimpleName());
        }

        System.out.println("checks=" + passed);
    }
}
```

Run with JDK 21+:

```bash
javac --release 21 -encoding UTF-8 IsolatePatternBugDemo.java
java IsolatePatternBugDemo
```

**Exact output** (the `shape-blank` line has three spaces right before the newline):

```text
PASS type-blank=type:Shipment
PASS shape-blank=shape:S-2:   
PASS guard-blank=guard:fail
REPRO blank expected=destination:missing actual=ship:
PASS fixed-valid=ship:Da Nang
PASS fixed-blank=destination:missing
PASS fixed-missing=destination:missing
PASS fixed-null-city=destination:missing
PASS fixed-null-selector=input:missing
PASS fixed-other=unsupported
PASS shape-null-destination=shape:miss
PASS shape-null-city=shape:S-4:null
PASS guard-valid=guard:pass
PASS missing-case-null=NullPointerException
PASS accessor-cause=IllegalStateException
checks=14
```

**Meaning of the results:**

- The first three lines are **three diagnostic layers**: type matches, nested record matches, business condition fails.
- The `REPRO` line proves the bug in `buggy(blank)`: actual `ship:` differs from expected `destination:missing`. That line must not be treated as a “passing production test”.
- The six `fixed-*` lines confirm the fix handles a valid address, whitespace, null nested record, null city component, null selector, and an unrelated type.
- The two `shape-null-*` lines prove that a **null nested record** is different from a **null component inside the nested record**.
- The two exception lines separate **NullPointerException from a null selector with no matching case** from **MatchException caused by a record accessor throwing an error** (the underlying cause is stored in `getCause()`).
- `checks=14` is the count of passing assertions in the non-intentionally-failing cases; `reproduceBug` alone does not increment the counter.

The example was run with Java 21 syntax and verified against specific cases. The entire program uses only the JDK, with no frameworks or auxiliary files needed.

## 6. Reading Results to Narrow the Scope, Not Just to “Turn Tests Green”

A proper investigation sequence might look like this:

| Test | Result | Valid Conclusion |
| --- | --- | --- |
| `typeOnly(blank)` | `type:Shipment` | Outer object has type `Shipment` |
| `shapeOnly(blank)` | `shape:S-2:   ` | Nested `Address` exists; `city` holds a three-space string |
| `guardOnly(blank)` | `guard:fail` | Business validity condition must reject this value |
| `buggy(blank)` | `ship:` | Current guarded branch still accepts whitespace |
| `fixed(blank)` | `destination:missing` | Fix satisfies the buggy case |
| `fixed(valid)` | `ship:Da Nang` | Fix does not break behavior for a valid address |

Note on inference order: from `typeOnly` passing, you **cannot** infer that the nested record pattern is right; from `shapeOnly` passing, you **cannot** infer that the guard is right; from the guard passing, you **cannot** infer that the branch body has no bugs. Each test only confirms the exact thing it checks.

This avoids a common investigation mistake: “the object is the right class, so `switch` must be broken”. In reality, the bug may be in `when`, component data, case ordering, or result-building logic.

## 7. When a Pattern Does Not Match: Distinguishing Type, Structure, and Guard

### 7.1. Wrong Outer Type

```java
Object candidate = Integer.valueOf(17);
boolean isShipment = candidate instanceof Shipment shipment;
```

`isShipment` is `false`. The record pattern `Shipment(...)` does not match either. There is no need to debug `Shipment` accessors further because this object is not a `Shipment`.

### 7.2. Null Nested Record

```java
Object candidate = new Shipment("S-3", null);

boolean deep = candidate instanceof Shipment(
        var shipmentId, Address(var destinationCity));
```

`deep` is `false`: the selector is a `Shipment`, but the nested record pattern `Address(...)` does not match `null`. Therefore `shapeOnly(missing)` returns `shape:miss`. This does not mean the selector itself is null, nor does it automatically throw an exception.

### 7.3. Null Component Inside a Nested Record

```java
Object candidate = new Shipment(
        "S-4", new Address(null));

boolean deep = candidate instanceof Shipment(
        var shipmentId, Address(var destinationCity));
```

In Java 21, the pattern `var destinationCity` can bind a `null` value of a reference component, so `deep` is `true`. If the guard only checks that `Address` exists without checking `city`, business logic may fail later.

### 7.4. Missing or Overly Broad Guard

A guarded pattern:

```java
case Shipment(var shipmentId, Address(var destinationCity))
        when destinationCity != null -> "ship:" + destinationCity.strip();
```

accepts `""` and `"   "`. If the contract requires a non-blank city, the validity condition must include `!destinationCity.isBlank()`. Because `&&` short-circuits, checking `destinationCity != null` first prevents calling `isBlank()` on null.

### 7.5. Bug in the Branch Body

If both the pattern and the guard match properly but the output is still wrong, create an independent test for the operation inside the branch body—for example, `" Da Nang ".strip()` or the application's actual calculation/formatter. Do not edit `case` when string concatenation, currency formatting, unit conversion, or an invoked service is the real source of the bug.

## 8. Preserving Data and Expected Behavior When Shrinking a Reproducer

A good **minimal reproducible example** has three properties:

1. **Minimal:** fewest data types, methods, and branches that still reproduce the bug.
2. **Reproducible:** re-running with the same input gives the same result under defined test conditions.
3. **Diagnostic:** the result lets you refute or confirm a specific hypothesis.

Shrinking does not mean changing semantics:
- If the bug involves `null`, do not replace null with `""` just to make the example look prettier.
- If the bug involves a null nested record, do not remove the nested record from the model and alter which branch matches.
- If the bug involves case ordering, keep at least the two cases that have a precedence relationship.
- If the bug involves an accessor throwing an exception, do not replace a record with a custom accessor with a record using only the default accessor.
- If the bug involves concurrency, mutable state, or I/O, write a fixture that can control those factors instead of removing the cause and making the bug disappear.
- If the bug is version-dependent, specify the exact `javac --release` and runtime.

To debug a multi-module program, you can start from a failing input in an integration test, write a unit test for a smaller method, and then reduce further to 1–2 records and a single `switch`. After fixing, you still need to run the integration test to ensure the fix handles real data and interactions properly.

## 9. When There Are Multiple Cases: Check Dominance, Ordering, and Exhaustiveness

In a `switch` with patterns, case order affects not only readability but also code validity.

**Intentionally non-compiling** example:

```java
return switch (candidate) {
    case Shipment(var id, var destination) -> "any shipment";
    case Shipment(var id, Address(var city)) -> "shipment with address";
    default -> "other";
};
```

Because the leading pattern `Shipment(var id, var destination)` already matches every `Shipment` instance (including null components), the subsequent `Shipment(var id, Address(var city))` case is **dominated**: it can never be selected. Java 21 reports a dominance error at compile time.

To isolate a dominance error, create a **minimal compilation** test containing only the two overlapping cases. You do not need to run the whole system to find a compiler error. The usual fix is to place the **specific pattern first, and the broader pattern after**:

```java
return switch (candidate) {
    case Shipment(var id, Address(var city)) -> "shipment with address";
    case Shipment(var id, var destination) -> "any shipment";
    default -> "other";
};
```

These are **illustrative snippets** using `candidate` and the declared `Shipment` record. Only change the order if it preserves the business contract: a specific pattern may match only a subset of the outer type's cases.

**Exhaustiveness** is a different error: a `switch` expression or enhanced `switch` statement with patterns must cover all possibilities of the selector type according to Java's rules. If a branch is missing for an open type like `Object`, a catch-all case is required. Still, “being exhaustive” **does not mean handling a null selector**. When a compile-time error occurs, distinguish `does not cover all possible input values` from `dominated case`, because the two errors have different causes and fixes.

## 10. Null Selector vs. Null Component: Test Separately to Find the Right Layer

Consider three objects:

```java
Object a = null;
Object b = new Shipment("S-3", null);
Object c = new Shipment("S-4", new Address(null));
```

| Input | Outer Object | Nested `Address` Record | `city` Component | Interpretation |
| --- | --- | --- | --- | --- |
| `a` | `null` | None | None | Null selector |
| `b` | `Shipment` | `null` | None | Null nested record |
| `c` | `Shipment` | Present | `null` | Null component of nested record |

A `case null` in `switch (candidate)` **only** handles `a`. It does not substitute for a case handling `b` or `c`. For `b`, the nested record pattern `Address(...)` does not match; for `c`, the pattern `Address(var destinationCity)` can match, with the component variable receiving null.

If a switch has no `case null`, a normal `default` does not handle a null selector, and the `switch` throws `NullPointerException`. The program in section 5 tests this situation with `noNullCase(null)` and verifies the exact exception type.

**Adding null tests at the right level** prevents misdiagnoses like “case null is broken” when the data is actually a non-null `Shipment` with a null `Address`.

## 11. Exceptions from Accessors: Do Not Treat as a “Mismatch”

A record can declare its own accessor with custom logic:

```java
record Fragile(String value) {
    public String value() {
        if (value == null) {
            throw new IllegalStateException("accessor failed");
        }
        return value;
    }
}
```

Evaluating `candidate instanceof Fragile(var value)` forces pattern matching to invoke the accessor to retrieve the component. If the accessor throws an exception during matching, Java 21 throws **`MatchException`**, wrapping the original exception in `getCause()`. This is not a case of `instanceof` returning `false` like a normal mismatch.

The test suite isolated this separately:

```java
try {
    fragilePattern(new Fragile(null));
    throw new AssertionError("MatchException expected");
} catch (MatchException expected) {
    assertEqual("accessor-cause", "IllegalStateException",
            expected.getCause().getClass().getSimpleName());
}
```

It shows the failure occurred during **accessor evaluation while matching**, not in `Shipment`'s guard. To debug further, inspect the accessor body and record data in a small test. Do not use `default` to “catch” accessor errors: matching terminated abnormally and does not fall back to another branch.

Conversely, if a **`when` guard** throws an exception, the exception from the guard propagates according to expression evaluation rules and does not automatically become a `MatchException` just because the guard is in a `switch`. An exception test should clarify whether it originated from the **selector expression**, **accessor during matching**, **guard**, or **case body**.

## 12. Pattern Variable Scope: Isolate with Minimal Compilation Code

Not every bug needs a runtime test. **Intentionally non-compiling** example:

```java
if (candidate instanceof Shipment shipment
        || shipment.destination() != null) {
    System.out.println("check");
}
```

The right-hand side of `||` can be evaluated when `candidate` is **not** a `Shipment`; `shipment` is not bound on that path. The compiler rejects using the variable.

If the goal is “is a Shipment and destination is non-null”, write:

```java
if (candidate instanceof Shipment shipment
        && shipment.destination() != null) {
    System.out.println("has destination");
}
```

The right-hand side of `&&` only runs when the left-hand side is true, so the pattern variable is validly in scope. To debug a scope error, reduce the condition to **one `instanceof` and one logical operator** and compile it. There is no need to create record fixtures or run tests if the error is a compile-time syntax/scope issue.

With `case Shipment(var shipmentId, Address(var destinationCity)) when ...`, the component variables can be used in the guard and the selected branch. However, do not use them in another case or after the switch if the compiler does not guarantee scope. Renaming variables does not solve scope errors; you must change the control-flow structure.

## 13. If Tests Have Side Effects: Freeze the Data Source Before Matching

A small test is only trustworthy when re-running it produces predictable results. Watch out for data sources with side effects:

```java
// Risk illustration: two calls may return two different objects.
if (queue.poll() instanceof Shipment) {
    Shipment shipment = (Shipment) queue.poll();
    process(shipment);
}
```

This is an illustrative snippet, assuming `queue` and `process` exist in the application. If `poll()` removes an element from the queue, the check and the cast use **two different elements**. Changing it to:

```java
if (queue.poll() instanceof Shipment shipment) {
    process(shipment);
}
```

evaluates `poll()` once, which may be the right bug fix, but it is **not** a purely behavior-preserving syntax change. If the bug depends on the number of reads, a small test should use a queue with two deterministic elements and assert the remaining element count.

To test pattern logic alone without pulling in side effects, **read once** into a stable variable:

```java
Object candidate = queue.poll();
if (candidate instanceof Shipment shipment) {
    process(shipment);
}
```

When extracting into a unit test, pass `candidate` as a directly constructed record object, with no dependency on network, database, randomness, or system time. Those dependencies are tested at a separate integration/contract layer.

Do not add `System.out.println` into an accessor or guard under investigation and conclude it has zero impact: logging itself is a side effect and in complex systems can alter execution timing. Prefer assertions, debuggers, and stable test data.

## 14. Using JUnit 5: Separating the Failing Test from the Fix

In a project using JUnit 5, you can encode expected behavior in unit tests:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PatternDebugTest {
    @Test
    void blankDestinationMustBeRejected() {
        var blank = new IsolatePatternBugDemo.Shipment(
                "S-2", new IsolatePatternBugDemo.Address("   "));
        assertEquals("destination:missing",
                IsolatePatternBugDemo.fixed(blank));
    }

    @Test
    void nullDestinationIsDifferentFromNullSelector() {
        var missing = new IsolatePatternBugDemo.Shipment("S-3", null);
        assertAll(
                () -> assertEquals("destination:missing",
                        IsolatePatternBugDemo.fixed(missing)),
                () -> assertEquals("input:missing",
                        IsolatePatternBugDemo.fixed(null))
        );
    }

    @Test
    void nullWithoutCaseThrowsNpe() {
        assertThrows(NullPointerException.class,
                () -> IsolatePatternBugDemo.noNullCase(null));
    }

    @Test
    void accessorExceptionRetainsCause() {
        MatchException ex = assertThrows(MatchException.class,
                () -> IsolatePatternBugDemo.fragilePattern(
                        new IsolatePatternBugDemo.Fragile(null)));
        assertInstanceOf(IllegalStateException.class, ex.getCause());
    }
}
```

This is an **illustrative test class, not a standalone runnable program**: it requires JUnit 5 and must be placed in the same package as `IsolatePatternBugDemo` (or have visibility adjusted). The methods and nested records in the main example have package-private access, so a test in the same package can call them.

To **prove the original bug with a red test**, replace `fixed(blank)` with `buggy(blank)` in the first test. Then `assertEquals("destination:missing", buggy(blank))` will fail because the actual value is `"ship:"`. After fixing production code, reuse this same test against the fixed production method; do not keep an intentionally failing assertion in CI.

### Do Not Write Empty “Check-the-Box” Tests

Weak test pattern:

```java
@Test
void weakTest() {
    IsolatePatternBugDemo.fixed(new IsolatePatternBugDemo.Shipment(
            "S-2", new IsolatePatternBugDemo.Address("   ")));
}
```

The test above only invokes the method and asserts nothing; it can easily pass even if the original bug remains. A useful debugging test needs:
- A specific input that exposes the bug.
- An expected value grounded in the contract.
- A clear assertion or exception expectation.
- A test name that describes the behavior.
- A non-bug control case to reduce the risk of fixing one branch while breaking another.

## 15. Red–Green–Refactor for Faulty Patterns

A short, repeatable workflow:

1. **Red:** write a test with expected behavior from the business requirements, showing the current version is wrong. For this article's bug, `blankDestinationMustBeRejected` calling `buggy` must fail.
2. **Isolate:** add `typeOnly`, `shapeOnly`, `guardOnly` tests to prove the fault is in the `when` condition, not in type checking or `Shipment` accessors.
3. **Fix:** change the exact guard `destinationCity != null` to `destinationCity != null && !destinationCity.isBlank()`.
4. **Green:** re-run the red test; it must pass. Run `valid`, `nullCity`, `missingAddress`, `nullSelector`, and `unsupported` cases to protect other behavior.
5. **Refactor:** if you want to restructure the switch or extract a method, do so in the next change while keeping all assertions green.
6. **Review:** explain why the new condition matches the contract; only add cases or `default` if genuinely needed, not to mask bugs.

You can use *mutation-oriented reasoning*: try removing `!isBlank()` from the fixed code. If the `fixed-blank` test does not fail, the test is not sensitive enough. Similarly, removing `case null` must make `fixed-null-selector` fail. You do not always need a dedicated mutation testing tool to apply this mindset.

## 16. Testing Across Layers: Unit, Compiler, and Integration

| Bug Type | Suitable Small Tool/Test | Success Signal |
| --- | --- | --- |
| Wrong input type | `instanceof` type pattern | Matches/mismatches as expected |
| Wrong nested record shape | `instanceof` record pattern | Distinguishes null nested record from null component |
| Guard missing condition | Boundary fixture + assertion | Empty/blank inputs rejected properly |
| Dominated case | Minimal program compiled with `javac` | Compiler reports dominance; case order fixed |
| Switch missing case | Compile test with matching hierarchy | Compiler accepts exhaustiveness |
| Null selector | `assertThrows` or `assertEquals` | Matches NPE/`case null` policy |
| Accessor throws error | Pattern on custom record + catch `MatchException` | Correct cause verified |
| Pattern variable scope | Minimal compilation snippet for `&&`/`||` | No more “cannot find symbol” error |
| Formatter bug in case | Unit test for string-building function | Expected text/amount matches |
| System interaction | Integration/contract test | Matching side effects and linked data |

A failing `javac` test is a test of **syntax/compile rules**, with no runtime stdout. A runtime behavior test requires the program to **compile successfully** and then compares expected/actual. Do not mix the two or use a compile error from an intentionally invalid snippet to claim that all runtime tests fail.

## 17. Symptom-Based Diagnostic Playbook

### Symptom A: “Data is present, but it does not enter the record case”

Ask in order: does the selector have the right outer type? Is the nested record null? Does the nested pattern require too specific a subtype? Is `when` wrong? Run `typeOnly`, `shapeOnly`, `guardOnly` with **the same fixture**.

### Symptom B: “Wrong case entered after adding a broad pattern”

Check ordering and dominance. A pattern like `Object` or `Shipment(var id, var destination)` may cover more values than the author intended. Test two inputs: one matching the narrow pattern and one matching only the broad pattern.

### Symptom C: “Null causes NPE even though default is present”

Check whether the selector is null or a dereference happened before the switch. If the selector is genuinely null, `default` usually does not handle it; you need `case null` or to accept NPE per the contract. Test the null selector case separately.

### Symptom D: “Record pattern throws MatchException”

Inspect custom accessors and `getCause()`. Do not blindly switch to another case; this may be an error **during matching** rather than a mismatch.

### Symptom E: “Replacing `instanceof + cast` with a pattern changed the result”

Count how many times the expression is evaluated, check branch ordering, and check the variable type passed to overloads. A source with side effects like `queue.poll()` may cause the new version to use a different object.

### Symptom F: “Pattern variable cannot be used”

Check flow scoping: `&&`, `||`, `!`, early `return`, case scopes, and duplicate variable names. If the compiler reports an error, do not try to debug at runtime before you have valid code.

## 18. Exercises and Answers

**Exercise 1 — Find the faulty layer.** `typeOnly(blank)` returns `type:Shipment`, `shapeOnly(blank)` returns `shape:S-2:   `, yet `buggy(blank)` returns `ship:`. Which step should you suspect first?

**Answer:** the guard `destinationCity != null` does not distinguish whitespace-only strings. Add `!destinationCity.isBlank()` and a regression test for `"   "`.

**Exercise 2 — Minimal reproducer.** To reproduce the bug above, do you need a real database, HTTP controller, and repository?

**Answer:** no. One `Shipment`, one `Address`, one switch, and one `"   "` input are enough to reproduce the bug. Integration components still need separate tests if they risk causing other bugs.

**Exercise 3 — Two forms of null.** Do `new Shipment("S-3", null)` and `new Shipment("S-4", new Address(null))` have the same deep-matching behavior?

**Answer:** no. The first causes the `Address(...)` pattern not to match; the second matches the `Address` record, while `var destinationCity` receives null. With the fix, both lead to the `destination:missing` branch.

**Exercise 4 — One bug case, one control case.** Why should you also test `" Da Nang "` after fixing the `"   "` bug?

**Answer:** to ensure changing the guard did not accidentally reject valid data with extra whitespace; expected must be `ship:Da Nang`.

**Exercise 5 — Compile error.** A `Shipment(var id, var destination)` case appears before `Shipment(var id, Address(var city))`. What can happen?

**Answer:** the narrow case is dominated by the broad case, which can cause a compile error. Create a two-case example, fix the order, and keep behavior tests after recompiling.

**Exercise 6 — Null selector.** Given `switch(candidate)` with only `case Shipment(...)` and `default`, what happens if `candidate == null`?

**Answer:** it normally throws `NullPointerException`. If the contract allows null, add `case null` and test that branch separately; do not assume `default` is a null fallback.

**Exercise 7 — MatchException.** In the `Fragile` example, how do you distinguish an accessor error from a normal pattern mismatch?

**Answer:** run a small test with only `Fragile(var value)`; if the accessor throws during matching, catch `MatchException` around the matching expression and verify `getCause()` is `IllegalStateException`. A normal mismatch simply returns false or goes to another case.

**Exercise 8 — False green test.** Why is a unit test that only calls `fixed(blank)` without an assertion weak?

**Answer:** it does not know which value is correct. The method could return `"ship:"` and the test would still report no failure. You need `assertEquals("destination:missing", fixed(blank))`.

**Exercise 9 — Post-refactor bug.** A function both checks `queue.poll() instanceof Shipment` and casts a subsequent `queue.poll()`. Does switching to a pattern variable preserve behavior?

**Answer:** not necessarily, because the number of `poll()` calls changes from two to one and the retrieved data may differ. You must test/evaluate the side-effect change separately instead of calling it a syntax-only refactor.

**Exercise 10 — Bug triage.** When should you use a compile test instead of a runtime test?

**Answer:** when the error is dominance, exhaustiveness, or flow scope preventing the code from compiling. Minimize type and case declarations so the compiler reports the error directly; only run runtime tests once you have valid code.

## 19. Takeaway Checklist

Before concluding you have isolated and fixed a pattern matching bug, check:

- [ ] Is there a small input that **reproduces** the exact symptom?
- [ ] Is Expected derived from the **business contract**, not copied from actual?
- [ ] Have you separated selector type, nested record shape, guard, and case body?
- [ ] Are there tests for **null selector**, **null nested record**, and **null component** when the model can encounter them?
- [ ] Have you distinguished compile errors, normal mismatches, and exceptions during matching?
- [ ] Have you checked case ordering, dominance, and exhaustiveness if using `switch`?
- [ ] Have you avoided depending on mutable data sources, time, randomness, or uncontrolled I/O?
- [ ] Does the fix have a regression test that was previously red and is now green, plus a non-bug control test?
- [ ] Does the test actually assert output/exception/side effects rather than just calling the method?
- [ ] Was it run with the exact Java version the code targets?

**Conclusion:** A small test is a tool for isolating root causes, not merely a shorter-line version of a large test. With Java pattern matching, separating **type → record structure → component value → guard → branch and result** helps pinpoint where the fault lies, avoids wrong fixes, and produces meaningful regression tests.

**Official documentation:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Patterns and Pattern Matching (`14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 — switch statement (`14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
