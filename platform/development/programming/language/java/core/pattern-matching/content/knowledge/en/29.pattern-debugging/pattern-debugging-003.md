# Tracing the Selected Case When Debugging Pattern Matching in Java 21

## 1. Goal: Knowing Which Branch **Actually** Ran

When using `switch` with type patterns, record patterns, and `when` guards, an input value can look similar to multiple different patterns. During debugging, you need to distinguish between three events:

1. **Pattern evaluated:** the runtime inspects a `case` label according to the `switch` selection rules.
2. **Pattern matched but guard false:** the data has the right type/structure, but the `when` condition returns `false`, so the next branch must be evaluated.
3. **Case selected:** the pattern matches (and the guard is true, if present); the branch body executes and produces a result or performs statements.

Only the third event directly answers the question **“which case was selected?”**. For example:

```java
return switch (value) {
    case String text when !text.isBlank() -> "Has content";
    case String text -> "Empty or blank string";
    default -> "Not a string";
};
```

With `value = "   "`, **the first `String` pattern matches by type**, but the guard `!text.isBlank()` returns false. The result is the **second case**, not the first. With `value = 42`, neither String pattern matches and `default` is selected.

Simply looking at the runtime type or placing logs in a shared handler method is not enough to know the exact path taken. You should have a way to identify the **case ID**, **relevant input or condition**, and **result**, without accidentally altering logic or logging sensitive data.

**Version:** Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) are standard features starting in **Java 21**. This article uses JDK 21+, without needing `--enable-preview`. The breakpoint, logging, and testing techniques also apply to traditional `switch`.

## 2. Branch Selection Mechanism in Switch Pattern Matching

An accurate mental model is:

```text
Selector value
    |
    v
Handle null selector if a matching case null exists
    |
    v
Evaluate case labels in order
    |
    +-- Pattern does not match ----> try next case
    |
    +-- Pattern matches
          |
          +-- Has when guard?
                |
                +-- false -------> try next case
                |
                +-- true / no guard
                         |
                         v
                   CASE SELECTED
                         |
                         v
                 Execute branch expression / block
                         |
                         v
               Yielded value or side effect
```

**Key points to note:**

- The `switch` selector is evaluated once, but the match result of each pattern and guard depends on the cases.
- In an enhanced `switch`, `null` requires an explicit policy. Do not assume `default` will catch a null selector; to handle it explicitly, use `case null`.
- A record pattern checks components structurally. If a component using a nested record pattern does not have the right type (including null), **the entire pattern does not match** and that case's guard does not run.
- `when` is evaluated only **after** the pattern matches. A guard returning false means continuing to search for a branch; it does **not** mean the case body ran.
- If a guard throws an exception, do not interpret it as “guard false”: the exception can exit the `switch`. If code in the branch body throws an exception, the branch was already selected, even though it may not produce a successful result.
- With arrow `->` branches, there is **no fall-through** between cases. With traditional colon `:` `switch statement` syntax, be mindful of fall-through behavior when `break` is omitted and the specific restrictions on pattern labels.
- With a `switch expression`, every selected branch must supply a value (or complete abruptly due to an exception). Inside a `-> { ... }` block, use `yield` to supply a value; in a regular `switch statement`, do not use `yield` to return a value for a statement.

An important distinction when recording traces: **“pattern evaluated”** is not **“case selected”**. Logging inside the executing branch or returning a **Case ID** is a more accurate way to observe it.

## 3. Approach 1 — Attaching an Explicit Case ID to the Result

When classification has an output, you can return a record containing the **branch code** and the **business result**:

```java
enum SelectedCase {
    NORMAL_TEXT,
    EMPTY_TEXT,
    OTHER
}

record Decision(SelectedCase selectedCase, String message) {}

static Decision decide(Object value) {
    return switch (value) {
        case String s when !s.isBlank() ->
            new Decision(SelectedCase.NORMAL_TEXT, s.strip());
        case String s ->
            new Decision(SelectedCase.EMPTY_TEXT, "(rỗng)");
        default ->
            new Decision(SelectedCase.OTHER, "khác");
    };
}
```

This snippet is a sample within the same class, requiring surrounding imports/domain types depending on the application; a complete standalone program is in section 7. With input `"  Java  "`, the case code is `NORMAL_TEXT` and the message is `"Java"`; with `" "`, the code is `EMPTY_TEXT`.

**Advantages:**

- Tests can assert `selectedCase()` directly, without having to parse log text.
- The branch code is `enum`-typed data, minimally coupled to display messages, translations, or output formatting.
- You can log **after** the `switch` returns the result; this keeps guards pure and avoids repeating log statements in every case.
- A request ID or trace ID can be attached at an outer layer without putting the entire payload into logs.

**Considerations:** it is not strictly necessary to add a `selectedCase` field to the public DTO of every API. In large applications, you can keep it in an internal result, a debug event, or a logging adapter, avoiding changes to external contracts solely for investigation.

## 4. Approach 2 — Logging Directly in the Case Body

When using a `switch statement`, each case can have a log statement at its entry point:

```java
// Illustration: logger, value, and handlers are already declared.
switch (value) {
    case String s when !s.isBlank() -> {
        logger.fine("selected=NONBLANK_STRING");
        handleText(s);
    }
    case String s -> {
        logger.fine("selected=BLANK_STRING");
        handleBlank(s);
    }
    default -> {
        logger.fine("selected=OTHER");
        handleOther(value);
    }
}
```

This is an **illustrative sample**, not a standalone program. With a `switch statement`, `->` makes it immediately clear which block belongs to which branch, without needing `break` at the end of each case.

In a `switch expression`, if you want to log inside a block, you must produce the value using `yield`:

```java
// Illustration: logger and value are available.
String result = switch (value) {
    case String s when !s.isBlank() -> {
        logger.fine("selected=NONBLANK_STRING");
        yield s.strip();
    }
    case String s -> {
        logger.fine("selected=BLANK_STRING");
        yield "(rỗng)";
    }
    default -> {
        logger.fine("selected=OTHER");
        yield "khác";
    }
};
```

**Advantages:** sees the selected case at the point of execution; easy to attach a breakpoint to the log statement. **Disadvantages:** repeated logging across many branches, which can scatter infrastructure concerns into business logic. If you only need to monitor the case name, an `Outcome` record with a branch code or an external tracking wrapper is usually less intrusive.

With `java.util.logging.Logger`, use the `FINE` level or equivalent to avoid spamming production; whether logs are displayed also depends on logger/handler configuration. Only use `System.out.println` for small demos, and do not treat it as a production tracing system.

## 5. Approach 3 — Breakpoint at the Start of Each Case

Using an IDE with a debugger (IntelliJ IDEA, Eclipse, VS Code with Java Debugger) or `jdb`:

1. Compile in debug mode (by default `javac` usually includes some debug info; you can specify `-g` explicitly when needed).
2. Set a breakpoint at the **first line of the branch body** you want to trace, or where the `Decision` containing the Case ID is created.
3. Run with a specific input; when paused, inspect the selector, pattern variables, record components, and relevant guard values.
4. Use step over/step into to trace the handler method being called. If the guard is in a helper, set a breakpoint inside the helper to see why it returned true/false.
5. Use a conditional breakpoint if you only want to pause when an ID or property meets a condition, but be careful of side effects in the condition expression.
6. When you suspect a branch is not being selected, set breakpoints in the **actually selected branch** and in the guard/helper; a breakpoint that does not hit does not by itself prove the cause.

**Situations to distinguish:**

- A breakpoint inside a **case body** does not hit if the pattern does not match or the guard is false.
- A breakpoint inside a **guard helper** can hit when the type pattern matches, even if the helper subsequently returns false.
- A breakpoint inside a **handler** confirms the handler was called, but may not distinguish between two cases if multiple cases call that same handler.
- If a guard/helper throws an exception, use an exception breakpoint to find the location and cause; do not mistake it for a fallback branch.

Do not rely absolutely on a one-to-one line number mapping between source and bytecode: the compiler may generate control flow different from how the pattern is written. When in doubt, verify with test inputs, breakpoints on explicit statements, and result traces, rather than guessing from debugger step jumps.

## 6. Name the Case, Do Not Infer It from Output Text

An unstable approach:

```java
// Do not treat display text as the technical identifier of a case.
if (result.startsWith("Ưu tiên")) {
    // Infer which case was selected?
}
```

When translations, templates, or formatting change, testing/debugging logic breaks. Moreover, **two branches can return the same string** while being selected for different conditions.

A clearer approach:

```java
record Outcome(Branch branch, String text) {}
enum Branch { PRIORITY, ORDINARY, MISSING_DATA }
```

Then check `outcome.branch()`. If used only for diagnostic logging, you can log `selected=PRIORITY` in one consistent place. The goal is to separate **“why this branch was entered”** from **“content displayed to the user”**.

Do not log full sensitive data just to identify a case: usually the **case ID, selector type, a correlation ID, and a few condition flags** are enough. IDs or payloads belonging to personal/order data must comply with the application's security, masking, and retention policies.

## 7. Complete Java 21 Example: Selecting a Case, Verifying the Result, and Tracing

This program intentionally includes easily confused branches:

- Priority `Shipment`: requires `Location` to be present, city non-null/non-blank, and priority high enough.
- `Shipment` with `Location` but **not eligible for priority**.
- `Shipment` missing `Location`, so both nested record patterns fail to match.
- `Message` with non-empty text, and remaining `Message`.
- Positive `Measurement`, and non-positive `Measurement`.
- `null` selector.

Instead of logging inside guards, each branch returns an `Outcome` with a `CaseId`. The `verify` method checks the selected case and prints only after the `switch` completes.

Create the file **`CaseSelectionTraceDemo.java`**:

```java
public class CaseSelectionTraceDemo {

    sealed interface Input permits Shipment, Message, Measurement {}

    record Location(String city) {}

    record Shipment(String code, Location location, int priority)
            implements Input {}

    record Message(String text) implements Input {}

    record Measurement(int value) implements Input {}

    enum CaseId {
        NULL_INPUT,
        PRIORITY_SHIPMENT,
        SHIPMENT_WITH_LOCATION,
        SHIPMENT_NO_LOCATION,
        NONBLANK_MESSAGE,
        OTHER_MESSAGE,
        POSITIVE_MEASUREMENT,
        OTHER_MEASUREMENT
    }

    record Outcome(CaseId selected, String description) {}

    static Outcome classify(Input input) {
        return switch (input) {
            case null ->
                new Outcome(CaseId.NULL_INPUT, "Đầu vào null");

            // Matches only when Location is non-null and the guard is true.
            case Shipment(var code, Location(var city), var priority)
                    when priority >= 5
                        && city != null
                        && !city.isBlank() ->
                new Outcome(
                    CaseId.PRIORITY_SHIPMENT,
                    "Ưu tiên " + code + " đến " + city);

            // Same record pattern but without a guard.
            case Shipment(var code, Location(var city), var priority) ->
                new Outcome(
                    CaseId.SHIPMENT_WITH_LOCATION,
                    "Có vị trí " + code
                        + " tại " + String.valueOf(city));

            // Location is null: both record patterns above fail.
            case Shipment shipment ->
                new Outcome(
                    CaseId.SHIPMENT_NO_LOCATION,
                    "Thiếu Location " + shipment.code());

            case Message(var text)
                    when text != null && !text.isBlank() ->
                new Outcome(
                    CaseId.NONBLANK_MESSAGE,
                    "Nội dung " + text.strip());

            case Message message ->
                new Outcome(
                    CaseId.OTHER_MESSAGE,
                    "Nội dung rỗng hoặc null");

            case Measurement(var value) when value > 0 ->
                new Outcome(
                    CaseId.POSITIVE_MEASUREMENT,
                    "Giá trị dương " + value);

            case Measurement measurement ->
                new Outcome(
                    CaseId.OTHER_MEASUREMENT,
                    "Giá trị không dương " + measurement.value());
        };
    }

    static void verify(Input input, CaseId expected) {
        Outcome outcome = classify(input);

        if (outcome.selected() != expected) {
            throw new AssertionError(
                "Expected " + expected + ", got " + outcome.selected());
        }

        // Trace only after classify completes:
        // one input, one CaseId, no logging inside guards.
        System.out.println(
            "case=" + outcome.selected()
                + " | " + outcome.description());
    }

    public static void main(String[] args) {
        verify(
            new Shipment("S-1", new Location("Hà Nội"), 8),
            CaseId.PRIORITY_SHIPMENT);

        verify(
            new Shipment("S-2", new Location("Huế"), 2),
            CaseId.SHIPMENT_WITH_LOCATION);

        // Priority guard is false because city == null, but nested
        // Location(...) still matches; the second case receives it.
        verify(
            new Shipment("S-3", new Location(null), 9),
            CaseId.SHIPMENT_WITH_LOCATION);

        // location == null causes nested Location(...) not to match.
        verify(
            new Shipment("S-4", null, 9),
            CaseId.SHIPMENT_NO_LOCATION);

        verify(new Message("  Java  "), CaseId.NONBLANK_MESSAGE);
        verify(new Message("  "), CaseId.OTHER_MESSAGE);
        verify(new Message(null), CaseId.OTHER_MESSAGE);
        verify(new Measurement(4), CaseId.POSITIVE_MEASUREMENT);
        verify(new Measurement(0), CaseId.OTHER_MEASUREMENT);
        verify(null, CaseId.NULL_INPUT);
    }
}
```

Compile and run in the directory containing the file using **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 -g CaseSelectionTraceDemo.java
java CaseSelectionTraceDemo
```

Exact expected output:

```text
case=PRIORITY_SHIPMENT | Ưu tiên S-1 đến Hà Nội
case=SHIPMENT_WITH_LOCATION | Có vị trí S-2 tại Huế
case=SHIPMENT_WITH_LOCATION | Có vị trí S-3 tại null
case=SHIPMENT_NO_LOCATION | Thiếu Location S-4
case=NONBLANK_MESSAGE | Nội dung Java
case=OTHER_MESSAGE | Nội dung rỗng hoặc null
case=OTHER_MESSAGE | Nội dung rỗng hoặc null
case=POSITIVE_MEASUREMENT | Giá trị dương 4
case=OTHER_MEASUREMENT | Giá trị không dương 0
case=NULL_INPUT | Đầu vào null
```

### 7.1. Why Is There No `default` in the Main Program?

`Input` is a `sealed interface` permitting only `Shipment`, `Message`, and `Measurement` in this example. The unguarded cases for each type cover all non-null instances of the subtypes; adding `case null` handles null. Therefore, the `switch expression` is **exhaustive** without needing `default`.

If the sealed hierarchy is extended with a new subtype, when existing cases do not cover that subtype, the compiler forces updating the `switch`. This is an opportunity to add a proper business case ID, rather than letting `default` mask a missing branch.

### 7.2. S-2: Pattern Matches but Guard Is False

S-2 has a structurally valid `Location("Huế")`, but `priority == 2` does not satisfy `priority >= 5`. The first case's guard returns false. The runtime evaluates the next branch with the same record pattern and no guard, and selects `SHIPMENT_WITH_LOCATION`.

**The correct trace must be the second case**, even though both the type and record shape of the first case matched.

### 7.3. S-3: Guard Is False Due to Null City

S-3 has a **non-null** `Location` with component `city == null`. `Location(var city)` matches and binds the `city` variable of type `String`, but its value can be null. The guard `priority >= 5 && city != null && !city.isBlank()` returns false at the null check, so it does not call `city.isBlank()`; no NPE is thrown.

The second `Shipment(..., Location(var city), ...)` case has no guard, so it is selected and the result displays the string `"null"` via `String.valueOf(city)`. This is **intentionally illustrating the difference between a null component and a null record**, not a recommended business formatting pattern. In a real system, you should decide whether a null city is an error, a valid absence, or a distinct state.

### 7.4. S-4: Nested Record Pattern Does Not Match

S-4 has `location == null`. The nested `Location(var city)` in both of the first two cases **does not match**, so **the priority case's guard does not run**. The remaining `case Shipment shipment` receives S-4 and returns `SHIPMENT_NO_LOCATION`.

If you only looked at `priority == 9` and concluded “it must be priority”, you missed the **structural condition**. In the debugger, you need to inspect both `location` and the `when` condition.

### 7.5. Message: Separating Pattern Match and Guard Failure

`Message("  Java  ")` matches the record, text is non-null and non-blank -> `NONBLANK_MESSAGE`. `Message("  ")` matches the record, but the guard `!text.isBlank()` is false -> `OTHER_MESSAGE`. `Message(null)` still **matches `Message(var text)`** because `var` accepts a null component; the guard `text != null` is false -> `OTHER_MESSAGE`.

### 7.6. Measurement: Value Condition Separated from Type

Both `Measurement(4)` and `Measurement(0)` have the same type. The guard `value > 0` identifies `POSITIVE_MEASUREMENT`; non-positive values go to `OTHER_MEASUREMENT`. Placing the guarded branch before the general branch is necessary to avoid dominance.

## 8. Debugging the Same Input with a Decision Table

When a case does not fall into the expected branch, do not look only at the final output. Build a state table following the branch order:

| Input | First Guarded Case | Reason to Continue or Select | Selected Case |
| --- | --- | --- | --- |
| `Shipment("S-1", Location("Hà Nội"), 8)` | Pattern matches, guard true | Has Location, high priority, valid city | `PRIORITY_SHIPMENT` |
| `Shipment("S-2", Location("Huế"), 2)` | Pattern matches, guard false | Priority less than 5 | `SHIPMENT_WITH_LOCATION` |
| `Shipment("S-3", Location(null), 9)` | Pattern matches, guard false | City is null, short-circuit prevents NPE | `SHIPMENT_WITH_LOCATION` |
| `Shipment("S-4", null, 9)` | Pattern does not match | Non-null nested Location is required | `SHIPMENT_NO_LOCATION` |
| `Message("  ")` | Pattern matches, guard false | Blank string | `OTHER_MESSAGE` |
| `Message(null)` | Pattern matches, guard false | `var text` can receive null | `OTHER_MESSAGE` |
| `Measurement(0)` | Pattern matches, guard false | Non-positive number | `OTHER_MEASUREMENT` |
| `null` | `case null` selected | Null selector has explicit policy | `NULL_INPUT` |

This table explains **why** a case is selected, while `Outcome.selected()` lets tests assert **which case** was selected. Combining both makes debugging more reliable than inferring from a generic message.

## 9. Where to Log Without Altering Case Selection Flow?

There are three observation points with different purposes:

| Log/Breakpoint Location | What You Learn | What It Does Not Prove by Itself |
| --- | --- | --- |
| Before `switch` | Input selector, context, correlation ID | The final selected case |
| Inside a helper called by `when` | The helper was called and the condition being evaluated | Whether the overall guard is true or the case was selected |
| First line of `case` body | This branch was actually selected | Why every preceding branch was not selected |
| After `switch` receiving `Outcome` with Case ID | The selected case and returned result | All intermediate checks, if there is no detailed trace |
| In `catch` surrounding `switch` | Exception escaped | Which case matched if the exception occurred before the case body |

**Recommendation:** first use **case identifiers + tests with boundary data**. Only when a Case ID does not match expectations should you add breakpoints in guards/helpers and inspect specific components. That is usually the approach with the fewest code changes.

### Do Not Put Side-Effect Logging Inside Guards Just for Tracing

A snippet like:

```java
// NOT RECOMMENDED for business code:
case Message(var text) when debugAndReturnTrue(text)
        && text != null && !text.isBlank() ->
    handleText(text);
```

can cause the guard to both mutate system state and return a boolean. If logging fails or the helper is impure, classification can be affected. Even if `debugAndReturnTrue` always returns true, the logic looks equivalent while still having side effects in the branch decision point.

Better approach: use a breakpoint in a **pure** check helper or log **after** receiving the outcome. Do not alter guard order, add expensive accessor calls, or evaluate an expression twice just to print values.

### Be Careful with Expensive Guards

If `when isEligible(input)` calls an external service or has side effects, debugging becomes unpredictable and may not remain deterministic. Consider extracting the business decision into a step with an explicit result type and testing on snapshot data. `when` should favor short conditions or pure, easily testable helpers.

## 10. Distinguishing Compiler Errors from Runtime Issues

There are branches that **cannot be selected right from the source**, and the Java 21 compiler can report an error due to dominance.

An **intentionally wrong example that does not compile**:

```java
return switch (input) {
    case Shipment shipment ->
        "Mọi Shipment";
    case Shipment(var code, Location(var city), var priority)
            when priority >= 5 ->
        "Ưu tiên"; // Dominated by the general Shipment branch.
    default -> "Khác";
};
```

`case Shipment shipment` already accepts every non-null `Shipment` object. The nested branch after it is unreachable; do not hunt for this issue with runtime logs—**read the compiler error and place specific branches before broad ones**.

For the same type, a valid order is:

```java
// Illustrative case labels, to be placed inside an appropriate switch.
case Shipment(var code, Location(var city), var priority)
        when priority >= 5 ->
    "Ưu tiên";
case Shipment shipment ->
    "Shipment còn lại";
```

Note that the first branch still requires a non-null `Location`; if location is null, the general branch handles it. The guard is only evaluated when the first pattern matches.

**Pattern variable scope** is also enforced by the compiler: `city` from the first case is only in scope within that `when` and that case body, not across other cases. Placing a log statement referencing `city` after the `switch` is invalid; to observe it, put the appropriate information into `Outcome` or log within the valid scope.

## 11. Switch Expression vs. Switch Statement When Debugging

| Criterion | `switch expression` | `switch statement` |
| --- | --- | --- |
| Purpose | Compute a value | Execute statements / side effects |
| `case T t -> expr` branch | Returns the expression's value | Valid as an expression statement when the expression is a statement expression |
| `-> { ... }` branch | Use `yield value` when returning a value from a block | Runs statements; no `yield` needed |
| Tracing case | Case ID in result is a convenient option | Log/breakpoint at start of block or shared callback |
| Fall-through | Does not occur | Arrow `->` form does not; traditional colon `:` form can |
| Exhaustiveness | Required to cover applicable cases | Exhaustiveness rules for enhanced switch statements must also be observed |

In this article, `classify` is a `switch expression`. It does one thing: **classify input into an outcome**. The `verify` method does the rest: comparing against the expected branch and emitting logs. This separation reduces the risk of auxiliary logging affecting branching logic.

## 12. Checklist for Debugging an Unselected Case

1. **Record the actual input** and runtime type, not just the expected value.
2. **Check whether the selector is null** and whether there is an appropriate `case null` or entry guard.
3. **Check case order**: is a general branch dominating a specific branch?
4. **Inspect the record tree from outside in**, especially null nested components.
5. **Distinguish `var component` from `Type(...)`**: `var` can hold null; a nested record pattern does not match null.
6. **Evaluate the guard on the actual data**: what type/value do pattern variables have, and which short-circuit condition stops early?
7. **Check if the guard throws an exception**: an exception is different from false.
8. **Set breakpoints in the actual branch body and guard helper**, do not infer solely from a breakpoint not hitting.
9. **Use Case IDs to assert** the selected branch; do not compare log text as the sole identifier.
10. **Check fallback/default** and input cases outside the sealed hierarchy or enum (if the API accepts a broad type).
11. **Compare output and side effects**: a selected case does not always mean the operation completed successfully.
12. **Retry with a small, deterministic test suite** to avoid depending on interaction history or data changing between runs.

### An Easily Missed Bug Pattern: Null in a Child Record

```java
record Address(String city) {}
record Delivery(Address address) {}

// Illustrative case labels:
case Delivery(Address(var city)) when city != null ->
    "Có thành phố";
case Delivery delivery ->
    "Delivery khác";
```

With `new Delivery(null)`, the first case does not match because `Address(...)` does not match null; the guard `city != null` **is not executed**. The second case is selected. If you want to log the missing-address state separately, you can use `case Delivery(var address) when address == null -> ...`, placed before the general case.

## 13. Regression Testing Instead of Only Reading Logs

A good test checks the **selected branch**, the **result**, and when needed, **side effects/exceptions**.

In the example in section 7, `verify` checks `Outcome.selected()`; if wrong, it throws `AssertionError` instead of just printing. To make it stronger, you can add an expected description:

```java
// Illustrative sample, in the same class as Outcome and classify.
static void assertOutcome(Input input,
                          CaseId expectedCase,
                          String expectedDescription) {
    Outcome actual = classify(input);
    if (actual.selected() != expectedCase
            || !actual.description().equals(expectedDescription)) {
        throw new AssertionError("Unexpected outcome: " + actual);
    }
}
```

With JUnit 5, you can write data-driven table tests to verify specific cases, though the project syntax depends on current JUnit dependencies and configuration. The standalone Java code in section 7 does not need JUnit and still provides simple automated verification.

**You should have tests for:**
- pattern + guard true;
- pattern match but guard false;
- null nested record causing pattern not to match;
- null `var` component where the record still matches;
- general case of the same type;
- null selector;
- boundary numbers (e.g., priority 4/5, value 0/1);
- exceptions in guards/handlers if allowed by the application;
- adding a new subtype to the sealed hierarchy and updating the exhaustive switch.

Do not claim that a matching Case ID means all business logic is tested: outputs and interactions with dependent systems still need corresponding checks.

## 14. Production Observability: Structured Logs and Data Protection

A useful trace log typically contains:

```text
traceId=...  operation=classify  selectedCase=PRIORITY_SHIPMENT
```

This is an **illustrative format sample**, not a specific ID. If the system processes many concurrent requests, a correlation/trace ID helps correlate logs. Logging **after the classification result is produced** can reduce discrepancies between “which case was selected” and “what value was emitted”.

Good practices:

- Use appropriate logger levels, adjusting sampling/verbosity in production to avoid excessive events.
- Keep Case ID names stable so dashboards/metrics do not depend on UI language.
- Do not log raw payloads, emails, specific addresses, tokens, or secrets when only the branch name is needed.
- Distinguish `selectedCase` from `operationStatus`; a selected branch does not prove DB/HTTP writes succeeded.
- If you want to count case selections, update metrics at the result-recording layer; do not insert side-effecting counter increments into guards.
- When changing branch order, update Case ID tests and monitor changes in case distribution during observed deployments.

## 15. Common Pitfalls

| Misconception | Reality | Fix |
| --- | --- | --- |
| “The type matched so the first case must run” | The guard can be false | Trace the guard and assert the Case ID |
| “Guard false means the case was entered” | Only the selected case's body executes | Log in the body / Outcome after switch |
| “A null nested record will still reach `when`” | Nested pattern fails to match before the guard | Check the component and capture with `var` when you want to handle null |
| “`var text` is always non-null” | The component can be null | Check for null before calling methods |
| “`default` handles all nulls” | Enhanced switch has special rules for null selectors | Explicit `case null` or guard before switch |
| “Need to log inside all guards” | Logging creates side effects in branch selection logic | Put Case ID in result, use breakpoints / pure helpers |
| “Two cases with the same output are the same case” | Same String does not identify the path taken | Use enum Case IDs or branch tags |
| “A case never runs even though tests are right” | May be compile-time dominance | Read compiler error and order specific before general |
| “Case ran means processing succeeded” | Handler/IO can fail after entering the case | Separate selectedCase from operation status |
| “Logging more data makes debugging easier” | Risks data exposure and creates noise | Log minimal relevant info, use masking |
| “`switch` expression has fall-through” | Arrow branches do not fall through | Check how branches return values / `yield` |
| “Debugger stopping in helper means branch selected” | The `when` helper can return false | Set breakpoint in case body or assert Outcome |

## 16. Exercises

**Exercise 1 — Predict the case.** Given `Shipment("S-5", new Location("Đà Nẵng"), 5)`, which Case ID is selected? Answer: `PRIORITY_SHIPMENT` because priority equals threshold 5 and city has content.

**Exercise 2 — Pattern fail or guard false?** Compare `Shipment("S-6", null, 8)` with `Shipment("S-7", new Location(null), 8)`. The first fails to match nested Location and selects `SHIPMENT_NO_LOCATION`; the second matches Location but fails the guard, so it selects `SHIPMENT_WITH_LOCATION`.

**Exercise 3 — Blank string.** Why is `Message("   ")` not selected as `NONBLANK_MESSAGE`, even though it has type `Message`? Explain the evaluation order of `text != null && !text.isBlank()`.

**Exercise 4 — Add a dedicated case for null city.** Add a `Shipment(..., Location(var city), ...) when city == null` case before the unguarded Shipment-with-Location case. Create a new `SHIPMENT_NULL_CITY` code and test S-3. Remember to consider its position relative to the priority case.

**Exercise 5 — Add a sealed subtype.** Declare `record Flag(boolean enabled) implements Input {}` and update `permits`. Observe the compiler requiring handling the new branch when `switch` has no `default`. Create Case IDs and tests for true/false values if needed.

**Exercise 6 — Using the debugger.** Set breakpoints at the `PRIORITY_SHIPMENT` result, in the `SHIPMENT_WITH_LOCATION` case, and in the guard/helper (if you extract a separate helper). For S-2, determine why the breakpoint in the priority branch does not hit.

**Exercise 7 — Logging and behavior.** If you add logging to a guard using an impure helper, list two risks. Propose a way to record `selectedCase` after classification without calling `classify` again.

**Exercise 8 — Separate branch and processing result.** Write an additional record `ProcessingReport(CaseId branch, boolean succeeded, String reason)` and explain why branch ID and success status are two separate properties.

## 17. Summary

To **trace the selected case**, do not infer solely from input type or output text. In Java 21:

- Both **pattern match** and **guard true** are required for a guarded branch to be selected.
- With nested record patterns, a null child record component can cause the pattern not to match, preventing the guard from being evaluated.
- `var` in a record pattern can hold a null component.
- Guarded cases should precede general cases of the same type to avoid dominance.
- `case null` expresses the null selector policy explicitly; arrow switches do not fall through.
- **Case ID in Outcome** and breakpoints in case bodies help observe the branch that actually ran; tests can assert the Case ID directly.
- Logging should be at the result point or branch body, avoiding side effects in guards; separate the selected case from the operation success status.

### References

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java Language Specification 21 — Switch statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — Switch expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
