# Reviewing Readability of Java Pattern Matching Solutions

## 1. Goal of the Capstone Exercise

After completing an exercise with `instanceof`, record patterns, or `switch` over a `sealed` hierarchy, the next question is not just "does the code compile and produce the right result?". A maintainer also needs to determine: **can someone else accurately understand the branches, conditions, and null contract of the solution without stepping through every line?**

A readable solution typically has these characteristics:

1. The reader quickly recognizes the **data type/domain** being processed.
2. Each `case` expresses a distinct business meaning; there are no hard-to-explain shadowed or duplicated cases.
3. Pattern variable names indicate the **role of the value**, not just short code.
4. Record patterns only deconstruct as deeply as actually needed; important data retains its context.
5. `when` describes short, pure, clear conditions, and there is a branch for when the guard is not satisfied.
6. The policy for **null selectors**, **null record components**, and exceptions is consistent and tested.
7. A `switch expression` has an easy-to-understand result type; `yield` only appears when a block needs multiple statements.
8. If refactoring for readability, **observable behavior must be preserved**, unless changing behavior is a separate requirement and is explicitly tested.

**Core principle:** *Readable does not mean fewer lines*. Reducing a solution from ten cases to one `Object o -> ...` case may be shorter, but it loses subtype information. Conversely, deconstructing every record component into variable names even when unused makes the code longer and harder to read.

This article uses **Java 21+**, because record patterns and pattern matching for switch are standard features as of Java 21. For plain `instanceof` type patterns, Java 17 already supports them. The focus is on **reviewing an existing solution and improving clarity**, rather than writing a completely different set of algorithms.

## 2. Review Scenario: Converting Support Requests into Display Labels

Suppose a helpdesk system has three types of requests:

- `CreateTicket(ticketId, title)`: create a ticket, requiring a non-empty title.
- `CloseTicket(ticketId, reason)`: close a ticket, requiring a non-empty reason.
- `EscalateTicket(ticketId, priority)`: route a ticket to a specialized queue; `priority` has `queueName` and `score`.

A `sealed` hierarchy describes the set of variants:

```text
TicketRequest (sealed interface)
├── CreateTicket   (record)
├── CloseTicket    (record)
└── EscalateTicket (record)
                      │
                      └── PriorityInfo(queueName, score) (record component)
```

Type declarations:

```java
sealed interface TicketRequest
        permits CreateTicket, CloseTicket, EscalateTicket {}

record CreateTicket(String ticketId, String title)
        implements TicketRequest {}

record CloseTicket(String ticketId, String reason)
        implements TicketRequest {}

record PriorityInfo(String queueName, int score) {}

record EscalateTicket(String ticketId, PriorityInfo priority)
        implements TicketRequest {}
```

This is a **structural illustration**; the standalone program in Section 7 places these types inside a class with `public static void main`.

Display contract for the exercise:

| Input | Expected Result | Meaning |
| --- | --- | --- |
| `null` selector | `request:missing` | No request |
| CreateTicket with non-blank title | `create:<id>:<stripped title>` | Display new ticket creation |
| CreateTicket with null/blank title | `create:invalid:<id>` | Missing useful title |
| CloseTicket with non-blank reason | `close:<id>:<stripped reason>` | Display close request |
| CloseTicket with null/blank reason | `close:invalid:<id>` | Missing useful reason |
| EscalateTicket with score from 90 | `escalate:critical:<id>:<queueName>` | Very high priority |
| EscalateTicket with score below 90 | `escalate:<id>:<queueName>` | Standard priority |
| EscalateTicket with null priority | `escalate:missing:<id>` | Missing priority record |

The `<...>` placeholders in the table describe the string structure, **not Java syntax**. Actual results in the program will use values like `T-1` or `risk`.

Here we **preserve the exact current contract**, including the case where `queueName == null` gets concatenated as the literal string `"null"`. In a production application you might want to forbid null `queueName` via validation, but that would be a **contract change**, which must not be silently mixed into a refactoring aimed solely at improving readability.

## 3. Initial Version: Correct but Hard to Review

Consider the following method:

```java
static String before(TicketRequest r) {
    return switch (r) {
        case null -> "request:missing";

        case CreateTicket(var x, var y)
                when y != null && !y.isBlank() ->
                "create:" + x + ":" + y.strip();

        case CreateTicket(var x, var y) ->
                "create:invalid:" + x;

        case CloseTicket(var x, var y)
                when y != null && !y.isBlank() ->
                "close:" + x + ":" + y.strip();

        case CloseTicket(var x, var y) ->
                "close:invalid:" + x;

        case EscalateTicket(var x, PriorityInfo(var z, var n))
                when n >= 90 ->
                "escalate:critical:" + x + ":" + z;

        case EscalateTicket(var x, PriorityInfo(var z, var n)) ->
                "escalate:" + x + ":" + z;

        case EscalateTicket(var x, var p) ->
                "escalate:missing:" + x;
    };
}
```

This is a **valid method** when placed in a class with the corresponding types. It has no syntax errors, and in the test examples it follows the stated contract. You should not claim "the code is wrong" just because the naming makes it hard for a reviewer to understand.

### Specific Readability Costs

**Overly generic names:** `r`, `x`, `y`, `z`, `n`, `p` force the reviewer to look up each record declaration. In `CreateTicket`, `x` is `ticketId` and `y` is `title`; in `CloseTicket`, `y` is `reason`. The same single-letter symbol carries different roles.

**Duplicated text-checking condition:** both `CreateTicket` and `CloseTicket` pairs check `y != null && !y.isBlank()` and then call `strip()`. If the display policy for both types is genuinely the same, duplication forces the reviewer to verify that the two pairs do not accidentally differ.

**Guards and fallbacks mixed at the same level:** the reviewer sees multiple consecutive cases and has to deduce that the second `Create`/`Close` case handles missing title/reason data, while the last `Escalate` case handles `priority == null`.

**Nested record pattern lacking semantics:** `PriorityInfo(var z, var n)` shows the type, but does not tell you that `z` is the queue name and `n` is the score. The threshold `90` is therefore hard to read because you do not see `riskScore` or `priorityScore`.

**Business rule scope is hidden:** the reader has to infer that "eligible for display" means a non-null, non-blank string; no name describes that policy.

**Correct parts to preserve:** the narrower guarded case precedes the broader case, `case null` is present, and the general `EscalateTicket` case handles a null priority component. Reviewers must not delete those branches just to make the code shorter.

## 4. Review Rubric: Measuring Clarity, Not Line Count

You can use a short rubric for code reviews. For each criterion, score **0–2**: 0 = hard to determine or clear risk; 1 = understandable but requires looking things up; 2 = reads naturally and is backed by tests. This is a discussion tool, **not a mandatory Java standard**.

| Criterion | What the reviewer looks for | Signs worth improving |
| --- | --- | --- |
| **Domain naming** | Variables reveal roles such as `ticketId`, `queueName` | `x`, `a`, `n` appear throughout |
| **Per-case intent** | Case immediately shows the variant and rule | Two cases look similar without explanation |
| **Deconstruction depth** | Only extracts components actually used | Record patterns nested 3–4 levels deep, many unused variables |
| **Case ordering** | Narrow/guarded before broad; no dominance issues | Parent pattern placed before child pattern |
| **Null/exception contract** | Null selector and null component are distinguished | `default` mistaken for catching null |
| **Result and side effects** | Switch expression produces one clear value | Helper hides I/O or mutates state inside a guard |
| **Duplication/abstraction** | Extracts repeated rules with shared semantics | Repeated logic or overly generic helper |
| **Testability** | Edge cases and expected values are clear | Only happy path tested, no value assertions |

**How to use it:** You do not need to sum scores into a KPI. Reviewers should note **concrete issues and specific suggestions**: "Rename `var n` to `var score` so the `>= 90` threshold is meaningful", instead of just commenting "code isn't clean".

The rubric also helps distinguish two types of comments:
- **Correctness blockers:** missing subtype, null handling violating the contract, guard throwing an exception, reordering cases in a way that changes behavior.
- **Readability suggestions:** variable names, extracting a helper, line breaks, comments explaining domain rules.

In a review, prioritize correctness first, then improve structure without breaking existing commitments.

## 5. Improved Version: Clear Names and a Purposeful Helper

The goal is to keep the exact output of `before(...)`, while reducing how much the reviewer has to "reverse-translate" variable names and repeated rules.

Extract the shared text-formatting policy:

```java
static String formatNonBlankDetail(
        String action, String ticketId, String detail) {
    if (detail == null || detail.isBlank()) {
        return action + ":invalid:" + ticketId;
    }
    return action + ":" + ticketId + ":" + detail.strip();
}
```

This is a **pure** helper in the sense that it does not mutate application state or query any service or database. It returns the exact string format already used in both `CreateTicket` and `CloseTicket` case pairs.

Update the solution to:

```java
static String after(TicketRequest request) {
    return switch (request) {
        case null -> "request:missing";

        case CreateTicket(var ticketId, var title) ->
                formatNonBlankDetail("create", ticketId, title);

        case CloseTicket(var ticketId, var reason) ->
                formatNonBlankDetail("close", ticketId, reason);

        case EscalateTicket(
                var ticketId,
                PriorityInfo(var queueName, var score))
                when score >= 90 ->
                "escalate:critical:" + ticketId + ":" + queueName;

        case EscalateTicket(
                var ticketId,
                PriorityInfo(var queueName, var score)) ->
                "escalate:" + ticketId + ":" + queueName;

        case EscalateTicket(var ticketId, var priority) ->
                "escalate:missing:" + ticketId;
    };
}
```

### Why Is This Version Easier to Read?

1. `request` makes it clear that the selector is a support request.
2. `ticketId`, `title`, and `reason` carry the exact component semantics.
3. `queueName` and `score` tell the reviewer that `score >= 90` checks the priority score.
4. The null/blank/strip string policy is centralized in `formatNonBlankDetail`, reducing repeated conditions.
5. The `EscalateTicket` cases remain in **critical → standard → missing priority** order, making the policy explicit.
6. `case null` still handles a null selector.
7. No `default` is added to mask new subtypes; the compiler still checks exhaustiveness of the sealed hierarchy.

**Trade-off to state explicitly:** the `formatNonBlankDetail` helper takes `action` as a string because the current example shares the same rule between creating and closing a ticket. If later `CreateTicket` needs to validate `title` differently from `CloseTicket.reason`, continuing to force both through the helper can tangle separate business rules. At that point, two domain-specific helpers or two separate explicit cases may be easier to read. **Do not extract a helper just to reduce line count.**

## 6. Before–After Comparison by Behavior, Not Just Intuition

Here is a minimal matrix to verify that the refactoring did not change the output:

| Input | Result of both `before` and `after` | Point to preserve |
| --- | --- | --- |
| `null` | `request:missing` | Null selector policy |
| CreateTicket with `"  Login fails  "` | `create:T-1:Login fails` | `strip()` whitespace |
| CreateTicket with `" \t "` | `create:invalid:T-2` | `isBlank()` |
| CreateTicket with `null` title | `create:invalid:T-3` | Do not call method on null |
| CloseTicket with `" solved "` | `close:T-4:solved` | Valid content |
| CloseTicket with `null` reason | `close:invalid:T-6` | Missing reason branch |
| EscalateTicket with score 90 | `escalate:critical:T-7:risk` | Inclusive `>= 90` boundary |
| EscalateTicket with score 89 | `escalate:T-9:risk` | False guard fallback |
| EscalateTicket with null priority | `escalate:missing:T-10` | Nested record does not match null |
| EscalateTicket with null queueName | `escalate:T-11:null` | Current string concatenation contract |

This table does more than prove "the two functions print the same thing". It forces the reviewer to determine **what the correct behavior is according to the requirements**. If both versions contain the same bug, a before/after comparison will pass; therefore, the test suite must compare **against the expected value from the spec**, not just `before(input).equals(after(input))`.

In the full program, each test verifies both simultaneously:

```java
Objects.equals(expected, before(input))
        && Objects.equals(expected, after(input))
```

If either differs from `expected`, the test throws `AssertionError`. After refactoring, when `before` is removed from production code, regression tests based on **contract-defined expected values** must still be kept.

## 7. Standalone Java 21 Example: Refactoring and 14 Checks

Save the entire example below as **`PatternReadabilityReviewDemo.java`**. This is a standalone program with `main`, using only the JDK. The records intentionally avoid deep validation so we can test null/blank values that a caller might construct. That is a characteristic of a learning fixture, not a recommendation to always allow invalid data in production.

```java
import java.util.Objects;

public class PatternReadabilityReviewDemo {
    sealed interface TicketRequest
            permits CreateTicket, CloseTicket, EscalateTicket {}

    record CreateTicket(String ticketId, String title)
            implements TicketRequest {}

    record CloseTicket(String ticketId, String reason)
            implements TicketRequest {}

    record PriorityInfo(String queueName, int score) {}

    record EscalateTicket(String ticketId, PriorityInfo priority)
            implements TicketRequest {}

    // BEFORE: same behavior, but uses hard-to-follow variable names and repeated guards.
    static String before(TicketRequest r) {
        return switch (r) {
            case null -> "request:missing";

            case CreateTicket(var x, var y)
                    when y != null && !y.isBlank() ->
                    "create:" + x + ":" + y.strip();
            case CreateTicket(var x, var y) ->
                    "create:invalid:" + x;

            case CloseTicket(var x, var y)
                    when y != null && !y.isBlank() ->
                    "close:" + x + ":" + y.strip();
            case CloseTicket(var x, var y) ->
                    "close:invalid:" + x;

            case EscalateTicket(var x, PriorityInfo(var z, var n))
                    when n >= 90 ->
                    "escalate:critical:" + x + ":" + z;
            case EscalateTicket(var x, PriorityInfo(var z, var n)) ->
                    "escalate:" + x + ":" + z;
            case EscalateTicket(var x, var p) ->
                    "escalate:missing:" + x;
        };
    }

    // AFTER: one helper with a clear contract for two actions sharing the same policy.
    static String formatNonBlankDetail(
            String action, String ticketId, String detail) {
        if (detail == null || detail.isBlank()) {
            return action + ":invalid:" + ticketId;
        }
        return action + ":" + ticketId + ":" + detail.strip();
    }

    static String after(TicketRequest request) {
        return switch (request) {
            case null -> "request:missing";

            case CreateTicket(var ticketId, var title) ->
                    formatNonBlankDetail("create", ticketId, title);

            case CloseTicket(var ticketId, var reason) ->
                    formatNonBlankDetail("close", ticketId, reason);

            case EscalateTicket(
                    var ticketId, PriorityInfo(var queueName, var score))
                    when score >= 90 ->
                    "escalate:critical:" + ticketId + ":" + queueName;

            case EscalateTicket(
                    var ticketId, PriorityInfo(var queueName, var score)) ->
                    "escalate:" + ticketId + ":" + queueName;

            case EscalateTicket(var ticketId, var priority) ->
                    "escalate:missing:" + ticketId;
        };
    }

    static int passed = 0;

    static void check(
            String name, TicketRequest input, String expected) {
        String original = before(input);
        String refactored = after(input);

        if (!Objects.equals(expected, original)
                || !Objects.equals(expected, refactored)) {
            throw new AssertionError(name
                    + " expected=" + expected
                    + ", original=" + original
                    + ", refactored=" + refactored);
        }

        passed++;
        System.out.println("PASS " + name + "=" + refactored);
    }

    public static void main(String[] args) {
        check("null-selector", null, "request:missing");

        check("create-valid",
                new CreateTicket("T-1", "  Login fails  "),
                "create:T-1:Login fails");

        check("create-blank",
                new CreateTicket("T-2", " \t "),
                "create:invalid:T-2");

        check("create-null",
                new CreateTicket("T-3", null),
                "create:invalid:T-3");

        check("close-valid",
                new CloseTicket("T-4", " solved "),
                "close:T-4:solved");

        check("close-blank",
                new CloseTicket("T-5", "   "),
                "close:invalid:T-5");

        check("close-null",
                new CloseTicket("T-6", null),
                "close:invalid:T-6");

        check("critical-boundary",
                new EscalateTicket(
                        "T-7", new PriorityInfo("risk", 90)),
                "escalate:critical:T-7:risk");

        check("critical-above",
                new EscalateTicket(
                        "T-8", new PriorityInfo("risk", 99)),
                "escalate:critical:T-8:risk");

        check("standard-below",
                new EscalateTicket(
                        "T-9", new PriorityInfo("risk", 89)),
                "escalate:T-9:risk");

        check("priority-null",
                new EscalateTicket("T-10", null),
                "escalate:missing:T-10");

        check("queue-null",
                new EscalateTicket(
                        "T-11", new PriorityInfo(null, 10)),
                "escalate:T-11:null");

        check("queue-blank",
                new EscalateTicket(
                        "T-12", new PriorityInfo(" ", 10)),
                "escalate:T-12: ");

        check("unicode-spaces",
                new CreateTicket(
                        "T-13", "\u2003Need help\u2003"),
                "create:T-13:Need help");

        System.out.println("TOTAL_PASS=" + passed);
    }
}
```

Compile and run:

```bash
javac --release 21 -encoding UTF-8 PatternReadabilityReviewDemo.java
java PatternReadabilityReviewDemo
```

**Output of all 14 cases when passing:**

```text
PASS null-selector=request:missing
PASS create-valid=create:T-1:Login fails
PASS create-blank=create:invalid:T-2
PASS create-null=create:invalid:T-3
PASS close-valid=close:T-4:solved
PASS close-blank=close:invalid:T-5
PASS close-null=close:invalid:T-6
PASS critical-boundary=escalate:critical:T-7:risk
PASS critical-above=escalate:critical:T-8:risk
PASS standard-below=escalate:T-9:risk
PASS priority-null=escalate:missing:T-10
PASS queue-null=escalate:T-11:null
PASS queue-blank=escalate:T-12: 
PASS unicode-spaces=create:T-13:Need help
TOTAL_PASS=14
```

Note: the `queue-blank` line ends with **one space** after the final colon. That is intentionally preserved to verify that the refactoring does not silently add a validation/normalization policy for `queueName`. If you copy the output through an environment that strips trailing whitespace, a visual diff might not accurately reflect the exact bytes/characters; the program itself uses assertions to check the strings.

The example was run using the Java compiler in `--release=21` mode, and the specific cases above produced the expected results. The number 14 is the count of passing `check` calls in `main`, not the number of `switch` cases.

## 8. What Does the Example Teach Us About Readability?

### 8.1. Variable Names Create a Link to the Domain

Compare:

```java
case EscalateTicket(var x, PriorityInfo(var z, var n))
        when n >= 90 -> ...
```

and:

```java
case EscalateTicket(
        var ticketId, PriorityInfo(var queueName, var score))
        when score >= 90 -> ...
```

Both are **illustrative snippets inside a switch** and cannot be compiled standalone with `...`. However, the second one shows what is being compared to 90 and why `queueName` is included in the label.

**Recommended rule:** name variables after the **role of the component at the point of use**, not just its Java type. Two components may both be `String`, but `ticketId` must not be named like `title` or `reason`.

Long names are not required: `score` is clear enough inside a `PriorityInfo` case, whereas `ticketId` should be distinct from `requestId` if the domain distinguishes the two IDs. Names should balance semantic clarity with conciseness.

### 8.2. Keep the Whole Object When Deconstruction Is Unnecessary

If you only need to forward the entire request to another handler:

```java
case CloseTicket closeTicket -> closeHandler.handle(closeTicket);
```

This is an illustrative label, assuming `closeHandler` exists. Using a **type pattern** preserves the `CloseTicket` context and avoids creating unused component variables.

Only use:

```java
case CloseTicket(var ticketId, var reason) -> ...
```

when you actually need `ticketId` or `reason` in that branch. Do not deconstruct a record just because the syntax allows it.

### 8.3. Stop Deconstructing at the Right Level

In `EscalateTicket`:
- Need `score`/`queueName` to classify → `PriorityInfo(var queueName, var score)` makes sense.
- Only need to know the request is an `EscalateTicket` → `case EscalateTicket escalation` is clearer.
- Need to check for null `priority` → a general pattern `EscalateTicket(var ticketId, var priority)` is meaningful.

If a record is nested four levels deep and a case only uses one value, you can extract a pure helper with a domain-specific name or use accessors directly after a type pattern. However, do not create arbitrary helpers if they only shuffle syntax and force the reader to jump across multiple files.

## 9. Guards, Dominance, and Case Ordering

A good pattern-matching review must distinguish **business conditions** from **matching order**.

### 9.1. Narrow Before Broad

Correct:

```java
case EscalateTicket(var id, PriorityInfo(var queue, var score))
        when score >= 90 -> "critical";

case EscalateTicket(var id, PriorityInfo(var queue, var score)) ->
        "standard";

case EscalateTicket(var id, var priority) ->
        "missing";
```

These are illustrative labels. The general unguarded pattern is placed after the more specific cases.

### 9.2. Wrong Ordering Example Rejected by the Compiler

Java 21 example **intentionally failing to compile**:

```java
public class ReadabilityDominanceCheck {
    sealed interface TicketRequest
            permits CreateTicket, CloseTicket {}

    record CreateTicket(String ticketId, String title)
            implements TicketRequest {}
    record CloseTicket(String ticketId, String reason)
            implements TicketRequest {}

    static String bad(TicketRequest request) {
        return switch (request) {
            case CreateTicket(var id, var title) -> "create:" + id;
            case CreateTicket(var id, var title)
                    when title != null -> "has-title";
            case CloseTicket(var id, var reason) -> "close:" + id;
        };
    }
}
```

The compiler reports an error like:

```text
this case label is dominated by a preceding case label
```

The reason is that the preceding unguarded `CreateTicket` case covers every `CreateTicket`, making the guarded case after it unreachable. This is a **compile-time error**, not a runtime bug that a reviewer might "ignore because nobody calls it".

Reorder them so the guarded case comes first and the fallback comes second, or combine into one case with an `if` in the body. Do not add `default` to work around dominance errors, as it does not change the dominance relationship between the two cases.

### 9.3. When a Guard Gets Too Long

`when` should express a readable condition with no side effects. With:

```java
when score >= 90
```

the intent is relatively easy to understand; however, if a guard makes multiple calls such as reading a database, checking permissions, getting the current time, logging, and mutating state, the reviewer cannot easily tell when matching is actually "true".

Prefer:
- Checking local, pure, short data directly in the guard.
- Putting multi-step business logic in the case body or a clearly named helper.
- Avoiding dependence on how many times a side-effecting helper is called during pattern/guard evaluation.
- In `&&` conditions, checking for null **before** dereferencing.

This improves both readability and debugging of exception paths.

## 10. Exhaustiveness Is a Review Tool, Not a Substitute for Business Logic

The hierarchy in this exercise has three direct records, all `final`. The `after` method has cases for all three types (some types have multiple narrow/guarded/fallback cases). Therefore, the compiler can prove the switch expression exhaustive without `default`.

**Benefit for reviewers:** If someone else adds:

```java
record ReopenTicket(String ticketId) implements TicketRequest {}
```

they must update `TicketRequest`'s `permits` clause for the subtype to be valid. Once the set of subtypes changes, an existing switch expression missing a path for `ReopenTicket` will be rejected by the compiler on recompile. This is an opportunity to review the new requirement rather than silently returning `unknown`.

**Do not over-interpret:** The compiler does not prove whether `"escalate:critical"` is the right policy. The threshold 90 is a business rule; you still need boundary tests, spec verification, and code review.

If an API intentionally has a `non-sealed` branch so external plugins can add subtypes, you need a case covering that open branch and a clear fallback policy. You cannot just list current concrete implementations and assume it will stay exhaustive forever.

## 11. Nulls and Exceptions: What Reviewers Must Separate

### 11.1. Null Selector

`after(null)` selects `case null` and returns `request:missing`. If you remove `case null`, `default` does not automatically handle null under Java 21 rules. Switching on a null reference normally throws `NullPointerException` if there is no matching null label.

This is a **public contract**: a refactoring must preserve returning this string, rather than replacing it with an NPE just to have fewer cases.

### 11.2. Null PriorityInfo Component

`new EscalateTicket("T-10", null)` is a non-null `EscalateTicket`. The nested `PriorityInfo(...)` pattern does not match a null component; the `EscalateTicket(var ticketId, var priority)` case still matches and returns `escalate:missing:T-10`.

This fallback branch is required for the existing contract. Deleting it and assuming "priority is always non-null" just because the normal domain expects it could make the switch non-exhaustive or change behavior for existing data.

### 11.3. Null and Blank Queue Name

With `PriorityInfo(null, 10)`, both before and after versions concatenate the string to `escalate:T-11:null`. With `PriorityInfo(" ", 10)`, the result has a trailing space.

This is not great formatting for a real UI; **however, it is the behavior of the original solution**, so a readability refactoring must not silently change it to `escalate:missing`. If you want to validate `queueName`, write a new requirement, decide when to throw an exception or fall back, and then update tests for the new contract.

### 11.4. Accessor Throwing an Exception

A record pattern needs to access components via their accessors. If a record declares a custom accessor and that accessor throws an error during matching, Java 21 may throw `MatchException` with the original exception in `getCause()`. That is a different failure path from "subpattern did not match because of null".

In this example, the default record accessors do not perform I/O or throw errors from custom logic. If you refactor a system whose accessors have side effects, you must test call order/count and the exception contract, not just the returned string.

### 11.5. Changes in Expression Evaluation

If previous code called the same method multiple times in `instanceof + cast`, switching to a pattern variable typically evaluates the source only once. This may be a bug fix, but it is still a **behavior change** if the method has side effects.

Reviewers should ask: "Is the pattern input a stable variable or a call that can mutate state?" If unsure, separate the change in evaluation count and add corresponding tests.

## 12. When to Extract a Helper, When to Keep Cases Inline?

A good helper carries a **stable meaning** or consolidates a **genuinely identical rule**.

In our example:
- `CreateTicket` and `CloseTicket` share the policy "detail is non-null and non-blank; if valid, strip it, otherwise invalid".
- `formatNonBlankDetail` consolidates that exact logic.
- The cases still show the domain names `CreateTicket` and `CloseTicket` right inside the switch, so the reader does not lose context.

However, if in the future `CloseTicket.reason` must preserve whitespace for auditing while `CreateTicket.title` still needs `strip()`, the shared helper becomes the wrong abstraction. Split it into `formatTicketTitle` and `formatClosingReason` or keep the logic where it belongs.

**Signs of a harmful helper:**
1. Generic names like `process`, `doIt`, `handleValue`.
2. Taking multiple boolean flags such as `isCreate`, `isClose`, `isUrgent`.
3. Using `Object` + casts to accept multiple types that already have distinct subtypes.
4. Performing I/O or mutating state despite having a formatter-like name.
5. Forcing the reviewer to open 3–4 files just to see what value a case returns.
6. Extracted solely because "the method is over 10 lines", with no shared concept.

**Review rule:** reduce duplication when duplication reflects the same rule; do not force two policies together just because they currently look similar in code.

## 13. Choosing the Right Construct: Switch Expression, Statement, Instanceof, or Visitor?

No single construct is optimal for every problem.

| Need | Usually Most Readable Construct | Why |
| --- | --- | --- |
| Transform a sealed value into another value | Exhaustive `switch expression` | All handled types are clearly visible |
| Classify a few types in a short method | `instanceof` type patterns / `if` | Avoids complex switch when branches are few |
| Perform multiple side effects per case | `switch statement` or dispatch to handlers | Avoids forcing every branch to return a value |
| Extract only 1–2 record components | Shallow record pattern or accessor | Avoids creating too many intermediate variables |
| Pass the whole object to a service | Type pattern keeping the object | Preserves context and type contract |
| System with subtypes extensible by plugins | Open registry/handler/interface | Does not assume a closed set of variants |
| Multi-step business rules | Clearly named service/helper | Keeps `when` short and limits side effects |

For example, an application service with four separate command handlers may be easier to review than a switch containing hundreds of lines of business logic. In that case, you can still use a short switch expression:

```java
return switch (request) {
    case CreateTicket create -> createHandler.handle(create);
    case CloseTicket close -> closeHandler.handle(close);
    case EscalateTicket escalation -> escalationHandler.handle(escalation);
};
```

This is an illustrative snippet, assuming the handlers exist and return compatible types. It intentionally does **not** deconstruct every component, because handling responsibility has been delegated.

If `request` is allowed to be null, add the null policy according to the contract; if null is forbidden, validate it before the switch. Readability only truly improves when responsibility boundaries are stated clearly.

## 14. How to Organize an Effective Review

You can review a pattern-matching solution in the following order to reduce repetitive comments:

### Pass 1 — Check the Contract and Correctness

Read the type hierarchy, `permits` list, branch expectations, and null policy. Determine whether the switch expression is exhaustive, which guards have fallbacks, and which edge-case inputs were overlooked. These issues must be addressed before renaming or reformatting.

### Pass 2 — Read Cases as a Decision Table

Convert the cases into a table:

| Case | Type/Condition | Behavior |
| --- | --- | --- |
| `null` | Null selector | Display missing |
| `CreateTicket` | Non-blank title | Display create |
| `CreateTicket` | Remaining | Invalid |
| `CloseTicket` | Non-blank reason | Display close |
| `CloseTicket` | Remaining | Invalid |
| `EscalateTicket` | Priority present, score from 90 | Critical |
| `EscalateTicket` | Priority present, score below 90 | Standard |
| `EscalateTicket` | Priority absent | Missing priority |

If a case cannot be summarized in one clear line, the reviewer can suggest naming a helper or separating the business rule. If two rows have the same meaning but different code, consider unifying them.

### Pass 3 — Read Variables and Scope

Check component names in the record, then read the pattern variables. Look for the same name used for different meanings, bound but unused variables, ambiguous names, or complex flow scoping. With `instanceof`, check `&&` and `||` to verify that a variable is definitely bound where it is used.

### Pass 4 — Check Evaluation Cost and Exceptions

Pattern matching can invoke record accessors, and guards can call helpers. Check for side effects, I/O, null dereferences, or changes in invocation count. If any exist, only restructure after protective tests are in place.

### Pass 5 — Verify Before/After Against Expected

Write fixtures for each case, edge-case data, null selector, null component, and the exception contract. Only then perform the refactoring. **A clean diff without regression tests does not prove a better solution.**

### Pass 6 — Express Actionable Feedback

Instead of: "This code is a bit hard to read", write:

> "In the `CreateTicket` and `CloseTicket` branches, variable `y` has two different roles and the non-blank guard is duplicated. Suggest naming them `title`/`reason` after the record components and extracting the shared display rule into a pure helper. Keep the null, blank, and whitespace test cases before changing."

This is an example of a code review comment that highlights the issue, the risk, and a concrete action.

## 15. JUnit 5: Turning Comparisons into Project Regression Tests

The program in Section 7 runs standalone without JUnit. If the project uses JUnit 5, you can write independent tests against the expected behavior, then remove `before` from production once the refactoring is accepted.

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PatternReadabilityReviewTest {
    @Test
    void titleMustBeNonBlankAndTrimmed() {
        var valid = new PatternReadabilityReviewDemo.CreateTicket(
                "T-1", "  Login fails  ");
        var blank = new PatternReadabilityReviewDemo.CreateTicket(
                "T-2", " \t ");

        assertAll(
                () -> assertEquals("create:T-1:Login fails",
                        PatternReadabilityReviewDemo.after(valid)),
                () -> assertEquals("create:invalid:T-2",
                        PatternReadabilityReviewDemo.after(blank))
        );
    }

    @Test
    void priorityBoundaryIsInclusive() {
        var at = new PatternReadabilityReviewDemo.EscalateTicket(
                "T-7", new PatternReadabilityReviewDemo.PriorityInfo(
                        "risk", 90));
        var below = new PatternReadabilityReviewDemo.EscalateTicket(
                "T-9", new PatternReadabilityReviewDemo.PriorityInfo(
                        "risk", 89));

        assertEquals("escalate:critical:T-7:risk",
                PatternReadabilityReviewDemo.after(at));
        assertEquals("escalate:T-9:risk",
                PatternReadabilityReviewDemo.after(below));
    }

    @Test
    void componentNullDiffersFromSelectorNull() {
        var missing = new PatternReadabilityReviewDemo.EscalateTicket(
                "T-10", null);

        assertAll(
                () -> assertEquals("request:missing",
                        PatternReadabilityReviewDemo.after(null)),
                () -> assertEquals("escalate:missing:T-10",
                        PatternReadabilityReviewDemo.after(missing))
        );
    }

    @Test
    void allKnownVariantsRemainCovered() {
        assertEquals("close:T-4:solved",
                PatternReadabilityReviewDemo.after(
                        new PatternReadabilityReviewDemo.CloseTicket(
                                "T-4", " solved ")));
    }
}
```

This is an **illustrative test class, not a standalone program**: it requires JUnit 5 and being in the same package as `PatternReadabilityReviewDemo`, or adjusting visibility. When the project is on Java 21, the code in Section 7 can be kept in a separate file as a JDK-runnable fixture before JUnit integration.

**Valuable test extensions:** add exception-contract checks if there are custom accessors, test the negative branch when score is 89, test cases for scores 90 and 91, test Unicode whitespace in both `title` and `reason`, and test parity on fixtures that affect the UI.

## 16. Common Review Mistakes and How to Fix Them

### 16.1. "Fewer cases is always better"

Fewer cases can hide important domain variants. With a sealed root, explicit cases are usually helpful. Only merge cases when they genuinely share one business rule.

### 16.2. "The deeper the record pattern, the better"

Multi-level patterns can make the reader lose context and create many unused variables. Use a type pattern or shallow deconstruction when the handler only needs the child object.

### 16.3. "Renaming variables is enough"

Good names help readability, but they do not fix guards missing fallbacks, exceptions, or side effects. A review must inspect both matching structure and behavior.

### 16.4. "Add `default` to avoid exhaustiveness headaches"

With a closed sealed hierarchy, `default` can hide the addition of a new subtype. A compiler error for a missing case is usually a useful **review prompt**, not an annoyance to suppress.

### 16.5. "`case null` handles all nulls"

`case null` handles a null selector, not a null component. A null `EscalateTicket.priority` requires a different case.

### 16.6. "Reordering or changing a guard makes no difference"

Guards and case order determine which path matches. A broad pattern before a narrow one can cause a dominance error; changing `>=` to `>` also alters boundary behavior.

### 16.7. "Extracting a helper always improves readability"

An overly generic helper can hide domain policies or side effects. If two rules differ, keep them separate; if they share the same rule, a specifically named helper makes sense.

### 16.8. "Testing that before and after match is enough"

If both return the wrong value according to the requirements, a parity test still passes. You need an independent expected value. The example suite checks both `original` and `refactored` against a single `expected` value.

### 16.9. "No need to test null because normal code always passes values"

An API accepting references can receive null if there is no constraint; record components can also be null. The contract should be clearly defined and tested.

### 16.10. "Reading a function means no side effects"

Patterns can invoke accessors and guards can call methods. If a custom accessor throws an exception or performs I/O, refactoring deconstruction can change when or what kind of error occurs.

### 16.11. "Java 17 code can use all Java 21 pattern syntax"

`instanceof String text` has been standard since Java 16, and `record` classes since Java 16; however, record patterns and pattern matching for switch became standard in Java 21. Reviews must note the exact `--release` and target JVM.

### 16.12. "Reviewers must like my coding style"

Personal style is not sufficient grounds to demand changes. Good feedback ties to domain clarity, correctness, tests, refactoring effects, and consistent team conventions.

## 17. Self-Practice Exercises with Answers

**Exercise 1 — Variable naming.** In `case EscalateTicket(var x, PriorityInfo(var z, var n)) when n >= 90`, how should the three names be changed?

**Answer:** `ticketId`, `queueName`, `score`. Those names show which data builds the label and what the 90 threshold evaluates.

**Exercise 2 — Null.** Why is `after(null)` different from `after(new EscalateTicket("T-10", null))`?

**Answer:** the first case is a null selector and matches `case null`; the second is an `EscalateTicket` instance where only the `priority` component is null. The nested `PriorityInfo` pattern does not match, so the general `EscalateTicket` case handles it.

**Exercise 3 — Boundary guard.** Does score 90 belong to the critical or standard branch?

**Answer:** critical, because the guard uses `>= 90`. You should have tests for scores 89 and 90 so it is not accidentally changed to `> 90`.

**Exercise 4 — Blank data.** Why is title `"  "` classified as invalid instead of being returned as an empty string after `strip()`?

**Answer:** the contract checks `isBlank()` before stripping. `isBlank()` on an all-whitespace string returns `true`, so the helper returns the invalid label.

**Exercise 5 — Shared helper.** When is `formatNonBlankDetail` no longer appropriate?

**Answer:** when `title` and closing `reason` have different policies—for example, `reason` must preserve whitespace while `title` is normalized. At that point, split the policies rather than forcing two rules into one helper.

**Exercise 6 — Dominance.** If you place an unguarded `CreateTicket(var id, var title)` case before a case with `when title != null`, how does the compiler react?

**Answer:** the guarded case after it is dominated by the preceding broad case; the Java 21 compiler rejects it.

**Exercise 7 — Record depth.** A handler only needs to log "received EscalateTicket request" and pass the whole request to a service. Should you write a type pattern or a nested record pattern?

**Answer:** the type pattern `case EscalateTicket escalation` is clearer, because it keeps the object and avoids deconstructing unused fields.

**Exercise 8 — Parity vs. correctness.** Both `before` and `after` return `create:T-1:` for an all-whitespace title. Does that prove the code is correct?

**Answer:** no. Both could be wrong in the same way. You need an expected value based on the contract, which here is `create:invalid:T-1`.

**Exercise 9 — API evolution.** If you add a `ReopenTicket` subtype to the sealed hierarchy, why should you avoid a blind `default`?

**Answer:** the compiler can flag exhaustive switches that do not yet handle the new subtype on recompile. A generic `default` can hide the need to decide a policy for the new type.

**Exercise 10 — Null queue name.** Why does the refactored version still allow `escalate:T-11:null` even though it is not pretty?

**Answer:** the goal is to improve readability while preserving current behavior. Validating `queueName` is a business change that must be requested and tested separately.

**Exercise 11 — Pure methods.** Why shouldn't `formatNonBlankDetail` write to a database or make network calls?

**Answer:** a formatting helper inside a switch should be predictable and free of side effects. I/O makes invocation count, failure points, and testing hard to reason about; responsibilities should be separated.

**Exercise 12 — Review comments.** Which comment is more useful: "bad code" or "`x` and `y` hide component roles; rename to `ticketId`, `reason` and keep null/blank tests before refactoring"?

**Answer:** the second one, because it pinpoints the issue, the risk, and an actionable fix.

## 18. Final Review Checklist

Before approving a Java Pattern Matching solution, a reviewer can ask:

- [ ] Do the names of the sealed root, subtypes, and pattern variables convey the domain?
- [ ] Can each case be summarized into one behavior in a single short sentence?
- [ ] Are all subtypes of the sealed hierarchy handled at the right level of detail?
- [ ] Are any cases dominated, or is narrow/broad ordering inverted?
- [ ] Are guards short, pure, easy to understand, and equipped with a path when false?
- [ ] Are deeply nested record patterns genuinely necessary?
- [ ] Is the whole object preserved when it only needs to be forwarded to a handler?
- [ ] Do null selectors, null nested components, and exceptions each have an explicit policy?
- [ ] Did we avoid accidentally changing accessor/helper call timing, side effects, or exception types?
- [ ] Does an extracted helper represent a real shared rule rather than a generic abstraction?
- [ ] Are the result type of the switch expression and `yield` usage clear?
- [ ] Are there independent expected-value tests to prevent both versions from being wrong together?
- [ ] Are boundary, null, blank, indirect subtype, and fallback paths adequately covered?
- [ ] Is the target Java release used accurately (record patterns/pattern switch: Java 21+)?
- [ ] If a new subtype is added, will the compiler and regression tests still catch missing handling?
- [ ] Is review feedback specific and verifiable?

**Conclusion:** Reviewing a solution's readability is not a code-golf contest. It is the process of clarifying **the meaning of each subtype, the deconstructed data, guard conditions, null behavior, and switch exhaustiveness**. A good refactoring lets readers predict behavior just by looking at names and structure, backed by a test suite proving that essential behavior has not changed.

**Official References:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Statements and Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [Java Language Specification 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
