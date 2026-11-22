# Writing guarded cases with `when` in Java 21 — comprehensive hands-on exercise

## 1. Exercise objectives

When using **pattern matching for switch**, a `case` branch may match the right type or data structure yet still need to satisfy an additional business condition. Java 21 provides the **guarded pattern label** syntax with the `when` keyword to express that idea directly:

```java
case SomeType value when condition -> result;
```

This **Writing guarded cases with `when`** exercise belongs to the **Comprehensive Practice** group. You will write a shipping request classifier consisting of three subtypes of a `sealed interface`: domestic shipping, international shipping, and pickup. Each subtype has guard-protected branches followed by a fallback branch for that same subtype. The exercise also builds skill in handling `null` at the root, `null` inside nested records, string checks, and boundary values; finally, a self-contained Java 21 program tests everything.

After this exercise, you will be able to:

- Write the `case Pattern when booleanExpression -> result` syntax correctly in a `switch`.
- Distinguish between a **pattern match** (matching type/structure) and a **true guard** (satisfying the additional condition).
- Use a record pattern to extract components and call validation functions from a guard.
- Place specific branches **before** general branches of the same type to avoid dominance errors or wrong priority order.
- Handle `null` properly and avoid `NullPointerException` in guards.
- Write an exhaustive `switch expression` over a sealed hierarchy **without adding `default` just to mask missing branches**.
- Design positive, negative, and boundary tests for each subtype, read compiler errors, and verify results with `javac --release 21`.

**Requirements:** JDK 21 or later to compile and run the sample code. **Record patterns** and **pattern matching for switch** are standard features in Java 21 (JEP 440 and JEP 441), requiring no `--enable-preview`. Type patterns in `instanceof` have been standard since Java 16 (JEP 394).

## 2. Problem statement: routing shipping requests

Implement the method:

```java
static String route(ShippingRequest request)
```

The method takes a shipping request and returns **a label string** according to the sample business rules in this exercise. The type set is closed using a `sealed interface`:

```java
sealed interface ShippingRequest permits Domestic, International, Pickup {}

record Address(String city, String country) {}

record Domestic(String id, Address address, int weightKg)
        implements ShippingRequest {}

record International(String id, String country, boolean customsReady)
        implements ShippingRequest {}

record Pickup(String id, boolean paid)
        implements ShippingRequest {}
```

These are **illustrative declarations**; the complete program in Section 6 declares everything inside a single Java class.

### Classification contract

| Subtype | Condition | Result |
|---|---|---|
| Root null | `request == null` | `INVALID:NULL` |
| Domestic | ID and city have text, country is exactly `VN`, weight is positive and at most 5 kg, city equals `HCM` case-insensitively | `DOMESTIC_EXPRESS:<id>` |
| Domestic | ID and city have text, country is exactly `VN`, weight is positive; does not meet express conditions | `DOMESTIC_STANDARD:<id>` |
| Domestic | Missing address, invalid fields, country other than VN, or non-positive weight | `INVALID:DOMESTIC` |
| International | ID/country have text and `customsReady == true` | `INTERNATIONAL_READY:<id>` |
| International | ID/country have text but `customsReady == false` | `INTERNATIONAL_PENDING:<id>` |
| International | ID/country is null, empty, or whitespace-only | `INVALID:INTERNATIONAL` |
| Pickup | ID has text and `paid == true` | `PICKUP_READY:<id>` |
| Pickup | ID has text and `paid == false` | `PICKUP_PENDING:<id>` |
| Pickup | ID is null, empty, or whitespace-only | `INVALID:PICKUP` |

These are **demo rules**, not a standard logistics system. For example, country codes are checked as strings, weight uses `int` to highlight boundary conditions, and the result is a string for testing. Production projects may require standard region codes, measurement units, idempotency, tracking, and dedicated services.

The goal of practicing `when` is to build **a prioritized chain of cases**: if a specific condition holds, select the narrow branch; otherwise, evaluate the next matching branch; finally, provide a fallback for the subtype.

## 3. Understanding the guarded case syntax

A `case` label with a guard in Java 21:

```java
case Domestic(var id, var address, var weightKg)
        when weightKg > 0 -> "POSITIVE_WEIGHT";
```

**This snippet is only an illustrative case label**, not a standalone program. Meaning:

1. The `switch` selector is a non-null `Domestic` object.
2. The record pattern deconstructs the components and binds `id`, `address`, and `weightKg`.
3. Only **after the pattern matches** is the boolean expression `weightKg > 0` evaluated.
4. If the guard is true, the right-hand side of `->` is executed.
5. If the guard is false, `switch` continues evaluating the subsequent case labels.

When the pattern does not match, the guard is not evaluated. Therefore, when debugging you should ask: **“Wrong subtype/structure, or right subtype with a false guard?”** — these are two different situations.

### Why use `when` instead of an `if` inside the case?

When there are multiple cases for the same subtype, guarded cases clearly express the **decision branches**, for example:

```java
return switch (request) {
    case Pickup(var id, var paid)
            when hasText(id) && paid -> "PICKUP_READY:" + id;
    case Pickup(var id, var paid)
            when hasText(id) -> "PICKUP_PENDING:" + id;
    case Pickup ignored -> "INVALID:PICKUP";

    // Other subtypes and the null case must be handled
    // for the switch expression to be exhaustive.
};
```

**This is an illustrative non-exhaustive switch** because Domestic and International are still missing. The complete program in Section 6 includes all branches.

How to read it like a decision table:

- Branch 1: Pickup with a valid ID, already paid.
- Branch 2: Pickup with a valid ID, not selected by branch 1.
- Branch 3: all remaining Pickups with invalid input.

This does not mean every `if` should be rewritten with `when`. If there is only a single check with a long body, an `if` inside a simple type pattern may be easier to read. Use `when` when it helps **compare possibilities for the same type side by side**.

## 4. Step-by-step practice: from unguarded to guarded cases

### Step 1 — Start with a subtype and a fallback

Write a simple branch:

```java
case Pickup pickup -> "PICKUP:" + pickup.id();
```

It matches every non-null `Pickup`, without distinguishing whether it is paid or not; even `pickup.id() == null` can still appear. This branch is useful for checking **subtype dispatch**, but it does not yet satisfy the problem requirements.

### Step 2 — Add a boolean condition with `when`

Extract fields using a record pattern and add a guard:

```java
case Pickup(var id, var paid)
        when hasText(id) && paid -> "PICKUP_READY:" + id;
```

This matches `Pickup` with a non-blank ID and `paid=true`. The `hasText` helper protects against null values.

### Step 3 — Add a branch for the remaining valid values

```java
case Pickup(var id, var paid)
        when hasText(id) -> "PICKUP_PENDING:" + id;
```

With `paid=false`, branch 1 has a false guard and branch 2 has a true guard, so it returns PENDING. With `paid=true`, branch 1 was already selected so branch 2 is not evaluated.

**Order is business logic.** If you put the “hasText” branch before the “hasText && paid” branch, a paid Pickup will return PENDING. The compiler does not necessarily recognize every logical relationship between guard expressions, so tests must prove the order.

### Step 4 — Add a same-subtype fallback

```java
case Pickup ignored -> "INVALID:PICKUP";
```

This branch matches any non-null Pickup **not selected by the guards above**. Use `ignored` when you do not need to access the components. Place it after the guarded branches. If placed first, the narrower branches below will be shadowed and the compiler may report `dominated case label`.

The `Pickup` trio above is the practice template: **narrow guard → broader guard → same-subtype fallback**.

### Step 5 — Apply to nested record patterns

For Domestic, an address is required:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when hasText(id)
             && hasText(city)
             && "VN".equals(country)
             && weightKg > 0
             && weightKg <= 5
             && city.equalsIgnoreCase("HCM")
        -> "DOMESTIC_EXPRESS:" + id;
```

Here it is important to distinguish **record levels**:

- `Domestic` must be non-null for the root pattern to match.
- `Address(...)` is a **nested record pattern**; if `address == null`, the entire deep pattern **does not match**, and the guard does not run.
- If `address` is non-null but `city == null`, `var city` can still **bind null** because it is a direct component. The guard `hasText(city)` returns false, so the branch is not selected.
- `"VN".equals(country)` is **null-safe** when country is null.
- `city.equalsIgnoreCase("HCM")` is only called after `hasText(city)` is true, so it does not dereference null.

The next step is the STANDARD case, omitting the express conditions:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when hasText(id)
             && hasText(city)
             && "VN".equals(country)
             && weightKg > 0
        -> "DOMESTIC_STANDARD:" + id;

case Domestic ignored -> "INVALID:DOMESTIC";
```

This structure **prioritizes express, then standard, and finally invalid**. It does not mean STANDARD “catches every request that fails express”: STANDARD **must still be valid** in terms of ID/city/country/weight. Requests with missing data must not fall into STANDARD.

### Step 6 — Apply to International

For `International(id,country,customsReady)`:

```java
case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country) && customsReady
        -> "INTERNATIONAL_READY:" + id;

case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country)
        -> "INTERNATIONAL_PENDING:" + id;

case International ignored -> "INVALID:INTERNATIONAL";
```

Reasoning: the READY branch has higher priority than PENDING. Both require ID and country to have text. Therefore, an International request missing a country is still INVALID even if `customsReady=true`.

### Step 7 — Handle null and exhaustiveness

Add `case null -> "INVALID:NULL"`. With the `sealed ShippingRequest` set of three subtypes, each subtype has an **unguarded fallback**, so every non-null value of the existing subtypes is handled.

**There is no need for `default`** just to satisfy the compiler. When a new permitted subtype is added and recompiled, the missing case should be reviewed — the compiler can report `switch expression does not cover all possible input values`. Adding `default` unnecessarily can mask the need to handle the new subtype.

## 5. Preparing the test dataset

Before looking at the full solution, build an input/expected table. The focus is that **every guarded case must have both an input that selects the branch and an input that makes its guard false**.

| Test | Request | Expected |
|---|---|---|
| Root null | `null` | INVALID:NULL |
| Domestic Express | Domestic("D1", Address("HCM","VN"), 1) | DOMESTIC_EXPRESS:D1 |
| Express at boundary | Domestic("D2", Address("HCM","VN"), 5) | DOMESTIC_EXPRESS:D2 |
| Heavier than boundary | Domestic("D3", Address("HCM","VN"), 6) | DOMESTIC_STANDARD:D3 |
| Other city | Domestic("D4", Address("HN","VN"), 2) | DOMESTIC_STANDARD:D4 |
| Lowercase city | Domestic("D5", Address("hcm","VN"), 2) | DOMESTIC_EXPRESS:D5 |
| Blank city | Domestic("D6", Address("  ","VN"), 2) | INVALID:DOMESTIC |
| Null city | Domestic("D7", Address(null,"VN"), 2) | INVALID:DOMESTIC |
| Null address | Domestic("D8", null, 2) | INVALID:DOMESTIC |
| Null ID | Domestic(null, Address("HCM","VN"), 2) | INVALID:DOMESTIC |
| Wrong country | Domestic("D9", Address("HCM","TH"), 2) | INVALID:DOMESTIC |
| Zero/negative weight | Otherwise valid Domestic, weight = 0 or -1 | INVALID:DOMESTIC |
| International ready | International("I1","JP",true) | INTERNATIONAL_READY:I1 |
| International pending | International("I2","JP",false) | INTERNATIONAL_PENDING:I2 |
| International blank/null country | International with missing country | INVALID:INTERNATIONAL |
| Pickup paid | Pickup("P1",true) | PICKUP_READY:P1 |
| Pickup unpaid | Pickup("P2",false) | PICKUP_PENDING:P2 |
| Pickup null/blank ID | Pickup with missing ID | INVALID:PICKUP |

The table above selects the key equivalence classes, while the complete program implements **24 independent test cases** with explicit expected strings. Return values are verified by assertions, not just printed to logs.

## 6. Complete solution: self-running Java 21 program

Save to **`GuardedWhenPracticeDemo.java`** (the file name must match the public class name). No libraries outside the JDK are needed.

```java
import java.util.Objects;

public class GuardedWhenPracticeDemo {
    sealed interface ShippingRequest permits Domestic, International, Pickup {}

    record Address(String city, String country) {}

    record Domestic(String id, Address address, int weightKg)
            implements ShippingRequest {}

    record International(String id, String country, boolean customsReady)
            implements ShippingRequest {}

    record Pickup(String id, boolean paid)
            implements ShippingRequest {}

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String route(ShippingRequest request) {
        return switch (request) {
            case null -> "INVALID:NULL";

            case Domestic(var id, Address(var city, var country), var weightKg)
                    when hasText(id)
                         && hasText(city)
                         && "VN".equals(country)
                         && weightKg > 0
                         && weightKg <= 5
                         && city.equalsIgnoreCase("HCM")
                    -> "DOMESTIC_EXPRESS:" + id;

            case Domestic(var id, Address(var city, var country), var weightKg)
                    when hasText(id)
                         && hasText(city)
                         && "VN".equals(country)
                         && weightKg > 0
                    -> "DOMESTIC_STANDARD:" + id;

            case Domestic ignored -> "INVALID:DOMESTIC";

            case International(var id, var country, var customsReady)
                    when hasText(id) && hasText(country) && customsReady
                    -> "INTERNATIONAL_READY:" + id;

            case International(var id, var country, var customsReady)
                    when hasText(id) && hasText(country)
                    -> "INTERNATIONAL_PENDING:" + id;

            case International ignored -> "INVALID:INTERNATIONAL";

            case Pickup(var id, var paid)
                    when hasText(id) && paid
                    -> "PICKUP_READY:" + id;

            case Pickup(var id, var paid)
                    when hasText(id)
                    -> "PICKUP_PENDING:" + id;

            case Pickup ignored -> "INVALID:PICKUP";
        };
    }

    static void test(String label, ShippingRequest input, String expected) {
        String actual = route(input);
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        test("root null", null, "INVALID:NULL");

        test("domestic express", new Domestic("D1",
                new Address("HCM", "VN"), 1), "DOMESTIC_EXPRESS:D1");
        test("domestic express limit", new Domestic("D2",
                new Address("HCM", "VN"), 5), "DOMESTIC_EXPRESS:D2");
        test("domestic standard heavy", new Domestic("D3",
                new Address("HCM", "VN"), 6), "DOMESTIC_STANDARD:D3");
        test("domestic standard city", new Domestic("D4",
                new Address("HN", "VN"), 2), "DOMESTIC_STANDARD:D4");
        test("domestic lowercase city", new Domestic("D5",
                new Address("hcm", "VN"), 2), "DOMESTIC_EXPRESS:D5");

        test("domestic blank city", new Domestic("D6",
                new Address("  ", "VN"), 2), "INVALID:DOMESTIC");
        test("domestic null city", new Domestic("D7",
                new Address(null, "VN"), 2), "INVALID:DOMESTIC");
        test("domestic null address", new Domestic("D8",
                null, 2), "INVALID:DOMESTIC");
        test("domestic null id", new Domestic(null,
                new Address("HCM", "VN"), 2), "INVALID:DOMESTIC");
        test("domestic blank id", new Domestic(" ",
                new Address("HCM", "VN"), 2), "INVALID:DOMESTIC");
        test("domestic other country", new Domestic("D9",
                new Address("HCM", "TH"), 2), "INVALID:DOMESTIC");
        test("domestic null country", new Domestic("D10",
                new Address("HCM", null), 2), "INVALID:DOMESTIC");
        test("domestic zero weight", new Domestic("D11",
                new Address("HCM", "VN"), 0), "INVALID:DOMESTIC");
        test("domestic negative weight", new Domestic("D12",
                new Address("HCM", "VN"), -1), "INVALID:DOMESTIC");

        test("international ready", new International("I1",
                "JP", true), "INTERNATIONAL_READY:I1");
        test("international pending", new International("I2",
                "JP", false), "INTERNATIONAL_PENDING:I2");
        test("international blank country", new International("I3",
                " ", true), "INVALID:INTERNATIONAL");
        test("international null country", new International("I4",
                null, true), "INVALID:INTERNATIONAL");
        test("international null id", new International(null,
                "JP", true), "INVALID:INTERNATIONAL");

        test("pickup paid", new Pickup("P1", true), "PICKUP_READY:P1");
        test("pickup pending", new Pickup("P2", false), "PICKUP_PENDING:P2");
        test("pickup null id", new Pickup(null, true), "INVALID:PICKUP");
        test("pickup blank id", new Pickup(" ", true), "INVALID:PICKUP");
    }
}
```

### 6.1. Compile and run commands

On JDK 21+:

```bash
javac --release 21 GuardedWhenPracticeDemo.java
java GuardedWhenPracticeDemo
```

**Verified actual stdout:**

```text
root null => INVALID:NULL
domestic express => DOMESTIC_EXPRESS:D1
domestic express limit => DOMESTIC_EXPRESS:D2
domestic standard heavy => DOMESTIC_STANDARD:D3
domestic standard city => DOMESTIC_STANDARD:D4
domestic lowercase city => DOMESTIC_EXPRESS:D5
domestic blank city => INVALID:DOMESTIC
domestic null city => INVALID:DOMESTIC
domestic null address => INVALID:DOMESTIC
domestic null id => INVALID:DOMESTIC
domestic blank id => INVALID:DOMESTIC
domestic other country => INVALID:DOMESTIC
domestic null country => INVALID:DOMESTIC
domestic zero weight => INVALID:DOMESTIC
domestic negative weight => INVALID:DOMESTIC
international ready => INTERNATIONAL_READY:I1
international pending => INTERNATIONAL_PENDING:I2
international blank country => INVALID:INTERNATIONAL
international null country => INVALID:INTERNATIONAL
international null id => INVALID:INTERNATIONAL
pickup paid => PICKUP_READY:P1
pickup pending => PICKUP_PENDING:P2
pickup null id => INVALID:PICKUP
pickup blank id => INVALID:PICKUP
```

There are **24 `test(...)` calls**, each with its own expected string. If a result differs from the contract, the program throws `AssertionError` and does not continue printing normally. The example was compiled directly with `javac --release 21` and ran successfully on all 24 cases.

**What is confirmed:** guarded case syntax, branch selection order, guard logic, `null` handling on the test data, and expected outputs. **What cannot be inferred:** that every real-world order is classified accurately, the validity of address standards, or that a production shipping system has complete validation. Those depend on domain-specific rules and additional tests.

## 7. Analyzing the results: what conditions select a case?

### 7.1. Domestic: express, standard, and invalid

In the express branch, the condition:

```java
hasText(id)
    && hasText(city)
    && "VN".equals(country)
    && weightKg > 0
    && weightKg <= 5
    && city.equalsIgnoreCase("HCM")
```

is a **short-circuit** boolean expression. For example, when `id == null`, `hasText(id)` is false; the remaining conditions are not evaluated. When `city == null`, `hasText(city)` is false and `equalsIgnoreCase` is never called, making it safe.

- **Domestic("D1",Address("HCM","VN"),1)**: right type, address exists, all express conditions true → EXPRESS.
- **Domestic("D2",Address("HCM","VN"),5)**: right at the 5 kg boundary, because the condition is `weightKg <= 5` → EXPRESS.
- **Domestic("D3",Address("HCM","VN"),6)**: express is false because weight exceeds 5 kg; standard is true because weight is still positive and the remaining conditions are valid → STANDARD.
- **Domestic("D4",Address("HN","VN"),2)**: express is false because city is not HCM; standard is true → STANDARD.
- **Domestic("D5",Address("hcm","VN"),2)**: `equalsIgnoreCase` returns true → EXPRESS.
- **Domestic("D8",null,2)**: nested `Address(...)` does not match null, so neither guarded Domestic branch is evaluated; `case Domestic ignored` returns INVALID.
- **Domestic with null or blank city**: Address exists, `var city` binds null/blank, but guard `hasText(city)` is false → INVALID.
- **Domestic with country other than VN or weight <= 0**: right subtype, but does not meet domestic shipping requirements under the demo contract → INVALID.

**Important:** `DOMESTIC_STANDARD` here is not a default for every Domestic request that fails express. It only accepts Domestic requests that are still **valid** in terms of ID, city, country, and weight. Writing guards this way distinguishes “not eligible for express” from “invalid data”.

### 7.2. International: readiness does not replace validation

The two International guards:

```java
case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country) && customsReady
        -> "INTERNATIONAL_READY:" + id;

case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country)
        -> "INTERNATIONAL_PENDING:" + id;
```

- `customsReady=true` but country is null/blank → both guards are false → INVALID.
- `customsReady=false` and valid data → READY guard is false; PENDING guard is true.
- `customsReady=true` and valid data → READY.

Do not write the READY branch with only `when customsReady` and skip validation: that would label requests with missing ID/country as READY. If policy requires the country to belong to a supported list, add a proper business validator rather than assuming `hasText(country)` is enough.

### 7.3. Pickup: distinguishing sub-conditions and fallback

`Pickup("P1",true)` and `Pickup("P2",false)` are both valid Pickups, but they receive different labels thanks to the guard. `Pickup(null,true)` still has subtype Pickup; the pattern `Pickup(var id,var paid)` matches the record, but `hasText(id)` is false so it falls back to INVALID.

When modifying the code, test **paid=true**, **paid=false**, **null ID**, and **blank ID** separately. If you only test paid=true, you will miss bugs in PENDING and the fallback.

## 8. Three typical compile-time errors when writing `when`

This section contains **intentionally broken files** to show compiler messages. Do not mix these files into the main program because they are designed **not to compile**.

### 8.1. Guarded case alone does not make a switch exhaustive

Create **`MissingFallback.java`**:

```java
class MissingFallback {
    sealed interface Job permits Build, Deploy {}
    record Build(int units) implements Job {}
    record Deploy() implements Job {}
    static String route(Job job) {
        return switch (job) {
            case Build(var units) when units > 0 -> "BUILD";
            case Deploy deploy -> "DEPLOY";
        };
    }
}
```

Run:

```bash
javac --release 21 MissingFallback.java
```

**Verified result:** `javac` rejects it because `Build(units <= 0)` is not covered by the cases; a guarded branch **does not guarantee that every value of Build makes the guard true**.

**Reasonable fix:** add a subtype fallback:

```java
case Build(var units) when units > 0 -> "BUILD";
case Build ignored -> "INVALID_BUILD";
case Deploy deploy -> "DEPLOY";
```

These are **case labels to replace inside the method**, not a separate Java file.

### 8.2. Placing a general case before a narrow case

Create **`DominatedGuard.java`**:

```java
class DominatedGuard {
    sealed interface Job permits Build {}
    record Build(int units) implements Job {}
    static String route(Job job) {
        return switch (job) {
            case Build build -> "ANY_BUILD";
            case Build(var units) when units > 0 -> "POSITIVE_BUILD";
        };
    }
}
```

Compile:

```bash
javac --release 21 DominatedGuard.java
```

**Verified result:** the compiler rejects the second branch due to a *dominated case label*. Because `case Build build` already matches every non-null Build, the trailing `Build(...) when ...` branch has no chance to run. Fix this by moving the guarded branch first and placing the general branch after it.

### 8.3. Using `when` after `instanceof`

Create **`InvalidWhenInstanceof.java`**:

```java
class InvalidWhenInstanceof {
    static boolean test(Object value) {
        return value instanceof String text when !text.isBlank();
    }
}
```

Compile:

```bash
javac --release 21 InvalidWhenInstanceof.java
```

**Verified result:** syntax error. In Java 21, `when` is used for **guarded `case` patterns in switch**, not chained after the `instanceof` operator.

With `instanceof`, use `&&`:

```java
static boolean isValidText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

The latter method is a valid example that can be placed in a Java class. The pattern variable `text` is in scope on the right-hand side of `&&` when the left-hand pattern matches.

## 9. Writing readable `when` clauses: from long expressions to named predicates

If a guard contains too many rules, it becomes harder to read than a clearly named method. Extracting validation such as:

```java
static boolean hasText(String value) {
    return value != null && !value.isBlank();
}
```

into a helper is useful because:

- The method name conveys intent: the value has non-blank text.
- Null-safe checking is applied consistently.
- Separate tests can be written for null/empty/blank/normal text.
- The guard stays focused on the routing decision instead of repeating `value != null` details in every case.

Similarly, if the domestic policy grows to include more region rules, maximum weights, item types, or delivery days, you can define a domain predicate:

```java
static boolean expressEligible(
        String id, String city, String country, int weightKg) {
    return hasText(id)
            && hasText(city)
            && "VN".equals(country)
            && weightKg > 0
            && weightKg <= 5
            && city.equalsIgnoreCase("HCM");
}
```

Then:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when expressEligible(id, city, country, weightKg)
        -> "DOMESTIC_EXPRESS:" + id;
```

These two snippets are **illustrative code fragments**, not part of the class in Section 6. The `expressEligible` predicate reproduces the exact express condition of the runnable program; if you use it, you must still ensure the STANDARD and INVALID branches exist. Extracting helpers should only be done when it **reduces cognitive complexity**, not to hide broken logic.

**A note on performance and side effects:** a guard is evaluated when its pattern matches, and may not be evaluated at all if an earlier case was already selected. Avoid putting network calls, data writes, metric increments, or state mutations inside a guard, because whether they run depends on case order and boolean short-circuiting. When handling side effects, select the case first and perform the action explicitly in the case body or an appropriate service.

## 10. Guard ordering and boundary conditions

### 10.1. When multiple guards are true at the same time

An Express request D1 satisfies both EXPRESS and STANDARD conditions. It is classified as EXPRESS because **the EXPRESS branch comes first**. When reading a pattern switch, examine the entire case order, not just individual guards.

Two guards may be logically related, yet the compiler **does not prove all algebraic or business relationships between boolean expressions**. Therefore, a misordered switch can still compile and return unexpected labels. Tests with data that satisfies multiple guards are mandatory.

### 10.2. Condition boundaries

In this exercise, weight `5` is Express, `6` is Standard, and `0` and `-1` are invalid. If someone changes `weightKg <= 5` to `weightKg < 5`, the `domestic express limit` test will fail.

When designing guard tests, include at least three points for every critical threshold: **below**, **at**, and **above**. For booleans like `paid` or `customsReady`, test both true and false; for nullable values, test null as well.

### 10.3. String comparison and locale

- `"VN".equals(country)` is case-sensitive and will not throw NPE if country is null.
- `city.equalsIgnoreCase("HCM")` ignores case differences but **does not trim**. `" HCM "` does not match HCM under this guard.
- `String.isBlank()` detects empty or whitespace-only strings per Java's definition, but **does not strip whitespace before other comparisons**.
- Do not casually replace conditions with `toLowerCase()` without a locale/normalization policy; that can change behavior for certain Unicode inputs.

### 10.4. When a fallback looks like it is “swallowing errors”

A broad default like:

```java
default -> "INVALID";
```

in a sealed command/request hierarchy loses information about which subtype failed. In this exercise, fallbacks have distinct names for Domestic, International, and Pickup. That helps tests and readers distinguish **which guard was not selected** from **an entirely new unhandled subtype**.

However, even a subtype-specific fallback only says that the request failed the contract; it does not explain the exact reason. If you need to report precise errors such as missing country, invalid weight, or missing ID, use a richer result model (such as `ValidationError`) rather than stuffing extra logic into guarded cases.

## 11. Testing when refactoring from `if/else` to `when`

A practical exercise is converting `if`-based code into a guarded switch **without changing behavior**. For example, a traditional Pickup method:

```java
static String routePickup(Pickup pickup) {
    if (!hasText(pickup.id())) return "INVALID:PICKUP";
    return pickup.paid()
            ? "PICKUP_READY:" + pickup.id()
            : "PICKUP_PENDING:" + pickup.id();
}
```

This is an illustrative method for **non-null** Pickup input. In the complete program, `switch` has its own policy for handling root null.

After converting to guarded cases, tests must prove:

- Null ID: no NPE and returns INVALID.
- Blank ID: returns INVALID.
- ID with text, `paid=true`: returns READY.
- ID with text, `paid=false`: returns PENDING.

The best evaluation is not merely comparing the outputs of the two versions; both versions could share the same bug. Define expected outputs from an independent contract, as in the `test(...)` method in Section 6.

In a production codebase, if a case touches a database or calls an external service, you must test **side effects** by subtype and state, because changing branch selection can cause effects beyond the returned string. This exercise only classifies into strings, so no side effects occur.

### Suggestion for migrating the dataset to JUnit 5

If JUnit Jupiter 5 is configured in your project, you can split the test cases into separate methods:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GuardedWhenPracticeTests {
    @Test
    void expressWeightAtBoundaryIsAccepted() {
        var input = new GuardedWhenPracticeDemo.Domestic(
                "D2", new GuardedWhenPracticeDemo.Address("HCM", "VN"), 5);
        assertEquals("DOMESTIC_EXPRESS:D2",
                GuardedWhenPracticeDemo.route(input));
    }

    @Test
    void missingNestedAddressUsesDomesticFallback() {
        var input = new GuardedWhenPracticeDemo.Domestic("D8", null, 2);
        assertEquals("INVALID:DOMESTIC",
                GuardedWhenPracticeDemo.route(input));
    }

    @Test
    void unpaidPickupIsPending() {
        var input = new GuardedWhenPracticeDemo.Pickup("P2", false);
        assertEquals("PICKUP_PENDING:P2",
                GuardedWhenPracticeDemo.route(input));
    }
}
```

**This is an illustrative JUnit snippet**, requiring the JUnit 5 dependency, the same package as the main class, and an appropriate test runner; it is **not** code compiled with `javac` without the JUnit classpath. The main program is the standalone example that was compiled and verified.

## 12. Common mistakes when writing guarded cases

| Mistake | Consequence | How to avoid |
|---|---|---|
| Using `when` after `instanceof` | Syntax error | Use `&&` with `instanceof`; use `case ... when ...` in switch |
| Placing a general subtype branch before a guard | Guarded branch is dominated or skipped | Put narrow guards first, fallback after |
| Only having guarded cases with no remaining branch | Switch expression may not be exhaustive | Add a same-subtype fallback per contract |
| Using `default` as a shortcut around exhaustiveness errors | New subtypes can be silently hidden | For sealed hierarchies, list the subtypes explicitly |
| Guard calls a method on a null component | Throws NPE | Place `hasText`/null guard first |
| Assuming a null nested Address still matches `Address(...)` | Wrong branch prediction | Remember nested record patterns do not match null |
| Assuming `var city` is always non-null | Misses leaf null | Test `Address(null, ...)` |
| Swapping EXPRESS and STANDARD guards | Express requests get classified as Standard | Test inputs that satisfy both |
| Not testing weight boundary values | `<` vs `<=` bugs go undetected | Test 4, 5, 6 kg and 0 |
| Using `||` instead of `&&` in validation | May accept inputs with missing fields | Write tests with each field null/blank |
| Putting side effects inside a guard | Depends on evaluation order, hard to debug | Separate classification from execution |
| Writing overly long, duplicated guards | Hard to modify and maintain | Extract named predicates when needed |

### Distinguishing compile-time vs. runtime

- **Compile-time errors:** invalid `when` syntax, inapplicable pattern, invalid pattern variable scope, dominated `case`, non-exhaustive switch expression.
- **Runtime no-match:** valid syntax, but selector is a different subtype, nested record is null, or guard evaluates to false.
- **Runtime exception:** e.g., calling a method on a null field when the guard did not protect it; not the same as no-match.
- **Wrong business result:** valid case and true guard, but wrong branch order or label selection rule.

When debugging, follow this order: **compiler → selector type/null → record structure → guard → case order → output**. Do not silence runtime surprises by adding `default` when the real issue is case ordering.

## 13. Additional practice exercises and verification guide

### Exercise A — Tighten the Express weight limit

Change the Express threshold from 5 kg to 3 kg while keeping all other conditions.

**Expected change:** `Domestic("D2", Address("HCM","VN"),5)` changes from `DOMESTIC_EXPRESS:D2` to `DOMESTIC_STANDARD:D2`. A weight of 3 remains Express. Update both the guard and expected tests accordingly, rather than editing code and deleting old tests.

### Exercise B — Add a priority city

To allow Express for city HCM **or** DN, change the final condition to:

```java
(city.equalsIgnoreCase("HCM") || city.equalsIgnoreCase("DN"))
```

**Keep `hasText(city)` before it**, and wrap the `||` group in parentheses so the shared ID, country, and weight conditions still apply to **both** cities. Writing `commonConditions && isHcm || isDn` could accept DN even with the wrong country/weight due to operator precedence.

**Suggested tests:** DN/1kg/VN → Express; DN/0kg/VN → Invalid; DN/1kg/TH → Invalid; DN/6kg/VN → Standard.

### Exercise C — Accept case-insensitive country code

Replace `"VN".equals(country)` with a predicate that states the policy clearly:

```java
static boolean vietnamCountry(String country) {
    return country != null && country.equalsIgnoreCase("VN");
}
```

When using this predicate in the guard, a test with `country="vn"` will change its result compared to the original version. **This is a business requirement change**, not merely formatting. Update expected outputs according to the approved decision.

### Exercise D — Add a new subtype

Add `record Locker(String id, boolean codeSent) implements ShippingRequest {}` and update `permits`. Before adding cases, run `javac --release 21`: the compiler will require an exhaustive handler for the new subtype. Then write:

```java
case Locker(var id, var codeSent)
        when hasText(id) && codeSent -> "LOCKER_READY:" + id;
case Locker(var id, var codeSent)
        when hasText(id) -> "LOCKER_PENDING:" + id;
case Locker ignored -> "INVALID:LOCKER";
```

**This is an extension suggestion** that must be added to the switch and fully declared; it is not compiled in the initial program. Test at least three cases: `codeSent` true/false and blank/null ID.

### Exercise E — Diagnose a buggy guard

Someone writes:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when hasText(id) && hasText(city)
             && "VN".equals(country)
             && weightKg >= 0
        -> "DOMESTIC_STANDARD:" + id;
```

Why can `weightKg == 0` be accepted?

**Answer:** because `weightKg > 0` was replaced with `weightKg >= 0`. The guard still looks valid and the compiler catches nothing; the `domestic zero weight` test will catch it.

### Exercise F — Migrating an `if` with side effects

If legacy code updates state after checking `if (paid)`, should that update operation be moved into `when`?

**Answer:** No. A guard should express a **condition**; side effects belong in the case body or a service. When branch order changes or a guard evaluates to false, side effects inside a guard can execute unexpectedly.

## 14. Checklist before finalizing a guarded switch

1. **Syntax:** Is the guard placed right after the case pattern with `when`, before `->`?
2. **Types:** Are the selector and pattern compatible at compile time?
3. **Records:** Do component patterns match the record's count, order, and types?
4. **Scope:** Are pattern variables only used in the guard and body of the branch where they are bound?
5. **Nulls:** Is there a clear policy for root null? Have nested record null and leaf null been tested?
6. **Guards:** Are conditions null-safe, using `&&`/`||`, parentheses, and short-circuit order properly?
7. **Order:** Are priority and specific branches first, with general fallbacks after?
8. **Exhaustiveness:** Does every subtype of the sealed type have a path, without adding unnecessary `default`?
9. **Boundaries:** Have you tested at the threshold and immediately on both sides?
10. **Labels:** Are expected outputs determined from an independent contract?
11. **Readability:** Does the guard clearly express policy, or should a clearly named helper be extracted?
12. **Side effects:** Are guards kept pure with no unintended operations?
13. **Build:** Does `javac --release 21` succeed with the proper file/class name?
14. **Regression:** Does each guarded case have at least one test that selects it and one test where its guard is false?

## 15. Self-check quiz

**1. Is `when` evaluated before or after the record pattern?**

After. If the pattern does not match, the guard is not evaluated.

**2. Does `Domestic("D8",null,2)` pass through a guard using `Address(...)`?**

No. A nested record pattern does not match when Address is null; the Domestic fallback handles it.

**3. Does `Domestic("D7",Address(null,"VN"),2)` fail for the same reason as a null address?**

No. Address exists and `var city` binds null; the guard `hasText(city)` evaluates to false.

**4. Why is `case Domestic ignored` needed even though there are already two guarded Domestic cases?**

Because both guards can be false. The fallback covers invalid Domestic requests and makes the switch exhaustive.

**5. Which branch does `Domestic("D2",Address("HCM","VN"),5)` enter?**

DOMESTIC_EXPRESS because of `<= 5`. Values equal to the threshold are accepted.

**6. Can you write `input instanceof String s when !s.isBlank()`?**

No. Use `&&` with `instanceof`; `when` belongs to guarded cases in a switch.

**7. What happens if a general Domestic case is placed before the guarded cases?**

The general branch matches Domestic first, dominating the narrower cases below it; the compiler may reject it.

**8. Why avoid adding `default` when a sealed hierarchy already has a fallback for every subtype?**

Because `default` can hide missing handling when a new subtype is added, defeating exhaustiveness checking.

**9. Can a guard be written with `||`?**

Yes. A guard is a boolean expression; use parentheses and watch short-circuiting and operator precedence so shared conditions are not accidentally bypassed.

**10. Why does a guarded switch that compiles still need unit tests?**

The compiler checks syntax, types, scope, and exhaustiveness; it does not prove that weight thresholds, priority cities, or validation conditions match requirements.

## Conclusion

Writing guarded cases with `when` works best when you structure decisions into **clear layers**: the pattern matches the subtype and data, the guard checks conditions, higher-priority branches come first, and a same-subtype fallback handles the rest. In Java 21, record patterns and sealed switches reduce casts, enforce exhaustive type checks, and keep rules close to the data.

In this exercise, the three subtypes Domestic/International/Pickup illustrate the full set of scenarios: true/false guards, nested records, root and component nulls, boundary conditions, short-circuiting, dominance, and exhaustiveness. Treat **independent expected-output tests** as a required part of the solution, not just an afterthought once the code compiles.

## Official references

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [Java Language Specification SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
