# Handling Unknown Enums in `default` in Java

## 1. What Does “Unknown Enum” Actually Mean?

When writing a `switch` on an `enum` type, learners often use `case` for states handled directly by the system and `default` for states without a dedicated branch. This seems simple, but the phrase “unknown enum” has at least **three different meanings**:

1. **The value is a valid enum constant that has not yet been listed in a `case`.** For example, `Status.ON_HOLD` is already declared in the enum, but the `switch` only has `NEW`, `RUNNING`, and `DONE`. With an explicit `default`, `ON_HOLD` will enter `default`.
2. **A new constant name is added to a library or enum in a later version.** Code compiled against the old list may encounter a constant added at runtime. An explicit `default` can provide fallback behavior, but at the same time reduces the compiler's ability to force the author to review every new state upon recompilation.
3. **External data is a string that does not exist in the enum.** For example, an API returns `"FUTURE"`, while the Java enum only has `NEW, RUNNING, DONE, ON_HOLD`. `Enum.valueOf(Status.class, "FUTURE")` throws `IllegalArgumentException`. **There is no corresponding `Status` object to pass into the `switch`, so the switch's `default` cannot catch this parsing error by itself.**

In addition, `null` is **not an enum constant** either and must be handled according to its own rule; `default` is not an automatic substitute for `null`.

This lesson focuses on **designing `default` when handling enums**, while explaining how to distinguish between a “constant without a case”, an “unparseable string”, and “null”. The goal is both to write syntactically valid code and to avoid hiding new business states.

### Decision Diagram

```text
Input data
   |
   +-- Already a Status? -- Yes --> status == null?
   |                                     |
   |                               Yes --> handle null
   |                               No
   |                                     |
   |                                     v
   |                              switch(status)
   |                                |-- matches case --> specific handling
   |                                +-- no match ------> default (if present)
   |
   +-- String from API?
           |
           +-- null/blank --> handle missing data
           |
           +-- parsed via valueOf --> Status --> switch
           |
           +-- parse failed --> handle invalid string
```

The diagram describes the processing flow, not Java syntax.

## 2. Enum Mechanics and Case Labels

Suppose we have order processing statuses:

```java
enum Status {
    NEW,
    RUNNING,
    DONE,
    ON_HOLD
}
```

`Status` is a Java enum class; each name in the enum body represents an **enum constant**. Constants have fixed identities according to their declared names. For a selector of type `Status`, case labels can be written using simple constant names:

```java
static String display(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        default -> "unhandled:" + status.name();
    };
}
```

This is an **illustrative method** that needs to be placed in a class with access to the `Status` enum. `case NEW`, `case RUNNING`, and `case DONE` match the corresponding constants. `ON_HOLD` does not match those three cases, so calling `display(Status.ON_HOLD)` produces `"unhandled:ON_HOLD"`.

The key point: `default` does not create a new “unknown” enum constant; it is merely a **fallback branch** when case label selection finds no specific label matching the given non-null value.

### Can `default` Replace Listing Constants?

No. Suppose the author actually wants to handle `ON_HOLD` as a paused state; returning `"unhandled:ON_HOLD"` is only a *fallback*. It does not contain specialized “pause order” behavior. Separate the two concerns:

- **Syntactically valid:** `default` gives the `switch expression` a fallback branch.
- **Business-correct:** `default` must return a safe result or explicitly reject; it should not silently pretend to be a fully handled state.

Placing `default` at the end usually helps readers recognize the policy for handling the remaining cases. When using `->` branches, cases do not fall through to the next case.

## 3. When Does a `switch expression` Require `default`?

A `switch expression` must be **exhaustive**: every valid value of the selector needs a branch that produces a result or throws an exception. For an enum, Java can prove exhaustiveness when **all currently known enum constants have a case**, because the set of constant names is finite at compile time.

### Case A — Not All Constants Listed: Fallback Needed

With `Status` having four constants, the following three cases do not cover `ON_HOLD`:

```java
// INTENTIONALLY INVALID regarding Java 17+ switch expression exhaustiveness:
static String incomplete(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
    };
}
```

The compiler reports that the `switch` expression does not cover all possible input values. There are two valid fixes: add `case ON_HOLD` with specific behavior, or add `default` with an intentional fallback behavior.

### Case B — All Constants Covered: `default` Not Required

```java
static String exhaustive(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        case ON_HOLD -> "on hold";
    };
}
```

This is an illustrative method. Java accepts the `switch expression` without `default` because it covers all four existing enum constants. Advantages:

- When a new constant is added to the enum and the `switch` code is **recompiled** against the new enum definition, the compiler can report a missing case, prompting the developer to decide its business meaning.
- Every current constant has dedicated handling, making it easy to test case by case.

Trade-off: if the runtime uses an extended enum while the code containing the `switch` **has not been recompiled**, there may be a constant not handled by any label. Under **Java 21** `switch expression` rules, a situation with no applicable label for a non-null value throws `MatchException`. You should not rely on a “hidden default” to automatically return a business value. In other Java versions, the error details when an enum changes out of sync may differ; this lesson is based on Java 21.

### Case C — All Cases Listed and `default` Still Written

```java
static String defensive(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        case ON_HOLD -> "on hold";
        default -> "unrecognized";
    };
}
```

This code is valid. `default` is currently not selected for the four declared values, but serves as a fallback branch if the binary environment introduces a new constant without a case.

**Trade-off:** Later, if `CANCELLED` is added and the code is recompiled, the compiler will not force adding `case CANCELLED` because `default` already covers it. Therefore, for behavior that must be reviewed when adding an enum constant, **omitting `default` is often more helpful**.

## 4. Complete Runnable Java 17 Example: `default` and Out-of-Enum Strings

Create `EnumDefault17.java`:

```java
import java.util.Locale;

public class EnumDefault17 {

    enum Status {
        NEW,
        RUNNING,
        DONE,
        ON_HOLD
    }

    static String display(Status status) {
        if (status == null) {
            return "missing";
        }

        return switch (status) {
            case NEW -> "new";
            case RUNNING -> "running";
            case DONE -> "done";
            default -> "unhandled:" + status.name();
        };
    }

    static String fromWire(String token) {
        if (token == null || token.isBlank()) {
            return "missing-token";
        }

        try {
            Status parsed =
                    Status.valueOf(token.strip().toUpperCase(Locale.ROOT));
            return display(parsed);
        } catch (IllegalArgumentException badToken) {
            return "invalid-token:" + token;
        }
    }

    public static void main(String[] args) {
        System.out.println(display(Status.NEW));
        System.out.println(display(Status.ON_HOLD));
        System.out.println(display(null));
        System.out.println(fromWire(" done "));
        System.out.println(fromWire("FUTURE"));
        System.out.println(fromWire(null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 EnumDefault17.java
java EnumDefault17
```

Exact output:

```text
new
unhandled:ON_HOLD
missing
done
invalid-token:FUTURE
missing-token
```

**Read the output carefully:**

1. `Status.NEW` matches its specific case and produces `new`.
2. `Status.ON_HOLD` **is a valid enum constant**, but has no specific case, so it enters `default` and returns `unhandled:ON_HOLD`.
3. `null` is handled **before the switch** via a pre-check, returning `missing`.
4. The string `" done "` is `strip()`ped, uppercased with `Locale.ROOT`, and then parsed into `Status.DONE`. Then `case DONE` produces `done`.
5. The string `"FUTURE"` **is not a constant name** in `Status`. `valueOf` throws `IllegalArgumentException`; `catch` returns `invalid-token:FUTURE`. The `switch` does not run, so `default` does not run either.
6. `null` from the string source is treated as a missing token and returns `missing-token`, not a parse error or an unhandled enum case.

`Locale.ROOT` normalizes casing independently of the user's locale; converting lowercase to uppercase is only **this example's parsing policy**, not the default behavior of `Enum.valueOf`. By default, `valueOf` requires an **exact name match** and is case-sensitive.

**Practical note:** The example returns the raw token in the error message to show the execution path. In real services, avoid putting untrusted data verbatim into logs or messages without length limits, sanitization, or structuring according to system conventions.

## 5. `default` Cannot Catch `Enum.valueOf` Errors

This is a very common design mistake:

```java
// WRONG if you expect default to catch the string "UNKNOWN":
static String parseWrong(String raw) {
    Status status = Status.valueOf(raw);
    return switch (status) {
        case NEW -> "new";
        default -> "fallback";
    };
}
```

This snippet is an **illustrative method**. With `parseWrong("UNKNOWN")` when `Status` has no constant named `UNKNOWN`, the `valueOf` call throws `IllegalArgumentException` **before** the `switch` runs. With `parseWrong(null)`, the `valueOf` call throws `NullPointerException` if not pre-checked.

The solution is to clearly define **two boundaries**:

- **External → enum boundary:** data from JSON, databases, query parameters, Kafka messages, etc., may contain unfamiliar names, wrong casing, whitespace, or null. Parse and handle data errors **here**.
- **Enum → behavior boundary:** after parsing into a valid constant, `switch` handles known constants, and `default` handles constants not listed in the cases.

A cleaner API option is to have the parsing layer return a structured result, such as a result type consisting of `Parsed(Status)` and `Invalid(raw)`, instead of conflating parse errors with a fallback enum constant.

### Do Not Use `valueOf` to “Dynamically Create New Constants”

A Java enum has a set of constants declared in the enum's source/bytecode. `valueOf` only **looks up** an existing constant; it does not create a constant when encountering a new string. `default` cannot be used to dynamically add new variants to an enum.

If business requirements need to store or display status codes from partners that the current software does not yet understand, **preserve the original string** in a result type or a separate field, rather than expecting the enum to hold arbitrary values.

## 6. `Enum.UNKNOWN` Is a Normal Constant, Not `default`

Some designs declare:

```java
enum Status {
    NEW,
    RUNNING,
    DONE,
    UNKNOWN
}
```

Here, `UNKNOWN` **is a real enum constant**. Therefore:

```java
static String explain(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
        case UNKNOWN -> "explicitly unknown";
    };
}
```

`case UNKNOWN` differs in meaning from `default`:

| Situation | `case UNKNOWN` | `default` |
| --- | --- | --- |
| Selector is constant `Status.UNKNOWN` | Matches | Only reaches `default` if no specific case matches |
| Selector is `Status.NEW` | No | May reach `default` if `NEW` has no case |
| Out-of-enum string `"FUTURE"` hits `valueOf` | No, because parsing did not produce `Status` | No, because `switch` has not run |
| Enum adds `PAUSED` | No | May match if `switch` has an explicit `default` and no `case PAUSED` yet |

If you want every unrecognized string name to become `Status.UNKNOWN`, you must **write a dedicated parsing policy** to perform that mapping. When doing so, consider the risk of **losing the original string name**, which makes diagnostics harder or loses the ability to handle it when a later version supports the new state.

For example, a parse function with a fallback to `UNKNOWN` is an **application decision**, not a default Java rule:

```java
static Status parseWithUnknown(String raw) {
    if (raw == null || raw.isBlank()) {
        return Status.UNKNOWN;
    }

    try {
        return Status.valueOf(raw.strip().toUpperCase(java.util.Locale.ROOT));
    } catch (IllegalArgumentException ignored) {
        return Status.UNKNOWN;
    }
}
```

This is an **illustrative method** assuming `Status` has the constant `UNKNOWN`. When you need to distinguish between `null`, blank strings, and unfamiliar names, use a richer result type instead of collapsing everything into `UNKNOWN`.

## 7. Java 21: Explicit `case null`, `default` for Remaining Enums

In Java 17, a `null` enum selector causes a `NullPointerException` in `switch` without a pre-check. `default` does not prevent this. Java 21 adds the ability to write `case null` in a switch on reference types, including enums.

Create `EnumDefault21.java`:

```java
public class EnumDefault21 {

    enum State {
        READY,
        RUNNING,
        FINISHED,
        WAITING
    }

    static String render(State state) {
        return switch (state) {
            case null -> "missing";
            case READY -> "ready";
            case RUNNING -> "running";
            case FINISHED -> "finished";
            default -> "unmapped:" + state.name();
        };
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "input-null";
            case State state -> render(state);
            case String raw -> "raw:" + raw;
            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe(State.READY));
        System.out.println(describe(State.WAITING));
        System.out.println(describe("FUTURE"));
        System.out.println(describe(42));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 --release 21 EnumDefault21.java
java EnumDefault21
```

Exact output:

```text
input-null
ready
unmapped:WAITING
raw:FUTURE
unsupported
```

### Two `switch` Layers Have Different Roles

- `describe(Object value)` uses the **type pattern** `case State state` to match an enum object and `case String raw` to match a string. Because the selector is `Object`, the **outer switch's `default`** handles objects of other types, such as `Integer`.
- `render(State state)` uses **enum constant cases** `READY`, `RUNNING`, `FINISHED`. `State.WAITING` is not among the specific cases, so it is handled by the **inner switch's `default`**.
- `describe("FUTURE")` does not call `Enum.valueOf`, because this program demonstrates input type classification. It returns `raw:FUTURE`, which does not mean the string was converted into a `State`.
- `case null` in the outer switch distinguishes a `null` input from `default`; `render` also has `case null` in case the method is called directly with `null`.

This example shows that **the `default` of a switch on `Object` and the `default` of a switch on an enum have different responsibilities**. Do not lump “unsupported Java type”, “unhandled enum constant”, “misnamed external string”, and “null” into the same error value if the business logic needs to distinguish them.

### Can `case null, default` Be Combined?

Java 21 supports `case null, default -> ...` when you genuinely want to combine both cases. However, for this topic, it is usually **better not** to combine them, because `null` may mean missing data whereas an enum's `default` is a valid constant not yet handled. That distinction is very useful in testing and diagnostics.

## 8. Java 17: A `switch statement` Can Silently Skip Constants Without a Case

Not every `switch` has the same exhaustiveness requirement. Consider a traditional `switch statement` on an enum:

```java
enum State { NEW, DONE, ON_HOLD }

static void printState(State state) {
    switch (state) {
        case NEW -> System.out.println("new");
        case DONE -> System.out.println("done");
    }
}
```

This is an **illustrative code snippet**. If `printState(State.ON_HOLD)` is called, no branch applies, so the method finishes **without printing anything**. In Java 21, a traditional-style switch statement (without pattern or `null` labels) can still be non-exhaustive to preserve source compatibility.

This differs from a `switch expression`, which must produce a result for every valid input. It also differs from a Java 21 *enhanced switch statement* that has patterns or a `null` label, because enhanced switch statements are subject to exhaustiveness rules.

When writing a switch statement on an enum for an important operation, choose one of two explicit approaches:

```java
switch (state) {
    case NEW -> startNew();
    case DONE -> finish();
    default -> handleUnhandled(state);
}
```

This is an **illustrative code snippet**: the three methods `startNew`, `finish`, and `handleUnhandled` must be defined. Without `default`, you should not assume Java will report a compile-time error for every unlisted constant in a traditional switch statement.

In contexts where a result is computed, a `switch expression` usually helps avoid forgetting to assign a value due to a missing branch.

## 9. Choosing a Policy for `default`: Fallback, Fail-Fast, or Fail-Closed?

`default` does not have to return a string `"UNKNOWN"`. It is where you express the **contract** when encountering an enum constant without a dedicated branch.

### 9.1. Display Fallback: Safe for Extensible Data

Suppose an application only needs to display a label for a status and can accept the raw constant name:

```java
static String label(Status status) {
    if (status == null) return "No status";
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "In progress";
        case DONE -> "Completed";
        default -> "Other (" + status.name() + ")";
    };
}
```

This is an **illustrative method** using the `Status` enum from earlier. Benefit: the UI is not disrupted when a new constant appears. Limitation: users may see a generic, untranslated, or business-inaccurate label. For systems with logging/metrics, you can record the new constant to plan adding a case.

### 9.2. Fail-Fast: Undefined Behavior for a State Is an Error

In financial logic, access control, or state machines, silently returning a false success can be dangerous. You can write:

```java
static String transition(Status status) {
    java.util.Objects.requireNonNull(status, "status");

    return switch (status) {
        case NEW -> "start";
        case RUNNING -> "continue";
        case DONE -> "stop";
        default -> throw new IllegalStateException(
                "Unhandled status: " + status.name());
    };
}
```

This is an **illustrative method**. For `ON_HOLD`, an exception is intentionally thrown. This turns an unhandled constant into a clear error signal, avoiding pretending to apply an inappropriate state transition.

However, when `default` is present, **after adding a new enum constant and recompiling**, the compiler no longer requires adding a new case. If the goal is to detect every variant accurately at compile time, consider **omitting `default` and listing every constant**, while testing enum updates.

### 9.3. Fail-Closed: Default Deny in Authorization

If an enum represents roles:

```java
enum Role { ADMIN, USER, GUEST, UNKNOWN }

static boolean mayDelete(Role role) {
    if (role == null) {
        return false;
    }

    return switch (role) {
        case ADMIN -> true;
        case USER, GUEST -> false;
        default -> false;
    };
}
```

This is an **illustrative code snippet**. The constant `UNKNOWN` falls into `default` and returns `false`. A role added later will also not automatically be granted delete permission unless an allowing case is added. This is the **fail-closed** principle: do not grant permission just because a branch is new or unrecognized.

Production designs still need appropriate logging/auditing and test suites, because a denying `default` does not replace an entire authorization model. Be cautious if choosing `default` to return `true` for any sensitive permission.

### 9.4. Logging and Measuring Unsupported Constants

When `default` acts as a fallback, there should be a way to observe it:

```java
default -> {
    System.err.println("Unhandled state: " + status.name());
    yield "Other";
}
```

This is a **Java 17+ branch snippet** inside a `switch expression`; when using a multi-statement block, `yield` returns the result for the expression. In real systems, rate-limited loggers/metrics are typically used, and untrusted data is not used as a metric label with unbounded cardinality.

Do not turn an observable fallback into a swallowed error that nobody notices, especially when a new state requires changing the processing workflow.

## 10. When an Enum Evolves: Trade-Offs

Suppose a library initially has:

```java
enum Approval { REQUESTED, APPROVED }
```

Application code uses a `switch expression` with two cases and no `default`:

```java
static String caption(Approval approval) {
    return switch (approval) {
        case REQUESTED -> "pending";
        case APPROVED -> "approved";
    };
}
```

At compile time, this expression is exhaustive and valid. Later, the library adds `REJECTED`. Two situations must be distinguished:

**Situation 1 — Recompiling the application against the new enum.** The compiler can report that the expression is not exhaustive and require deciding how to handle `REJECTED`. This is the **advantage of omitting `default`**: model changes force corresponding code changes.

**Situation 2 — Swapping the enum library at runtime while keeping the already-compiled application classes.** If an `Approval.REJECTED` object reaches `caption` where the old labels do not apply, Java 21 can throw `MatchException` per switch expression rules. Therefore, library upgrade workflows should **rebuild and test dependent modules**. Do not treat the binary compatibility of adding an enum constant as proof that every execution path is meaningful.

If the expression had `default -> "other"` from the start, it could accept `REJECTED` and continue. This increases fault tolerance when encountering new variants, but the compiler will not force adding an explicit case after the enum is extended.

### Quick Selection Rules

| Goal | What should `default` do? | Trade-off |
| --- | --- | --- |
| Non-critical display, want to keep operating | Return a safe label and record the new constant | May lack specialized behavior/wording |
| State machine, critical business logic | Intentionally `throw` or handle as a business error | May interrupt, but prevents wrong state updates |
| Authorization | Deny by default (`false`/deny) | Needs auditing to distinguish config errors from new roles |
| Want compiler to enforce handling when enum adds constants | List all cases, **no `default`** | Requires recompilation when enum changes; old binaries may fail on new constants |
| String data from external systems | Parse separately, return error result or keep raw token | Not the job of switch `default` |

There is no single right default choice for every project. State the **contract clearly** and test adding a constant in both code reviews and test suites.

## 11. Relationship with Pattern Matching in Java 21

Enums can appear in Java 21 in two different ways:

**Approach A — The selector is the enum type itself:** use **constant labels** like `case NEW`, `case DONE`. There is no need for a type pattern to check the type of a selector that is already `Status`.

**Approach B — The selector is a broader type such as `Object`:** you can use a **type pattern** `case Status status` to bind the enum object, then call a dedicated enum `switch`:

```java
static String process(Object input) {
    return switch (input) {
        case null -> "missing";
        case Status status -> display(status);
        case String raw -> "unparsed token: " + raw;
        default -> "wrong data type";
    };
}
```

This is a **Java 21** illustrative method, assuming `Status` and `display(Status)` are defined. `case Status status` does not classify individual constants by itself; it only matches objects of type `Status`, and then `display` branches on the enum constants. The two levels of `default` have distinct meanings: “unsupported Java type” and “constant without dedicated handling”.

If you want to use `when` to filter a subset, you can write:

```java
case Status status when status == Status.ON_HOLD -> "on hold";
case Status status -> display(status);
```

These are **labels in `switch(Object input)`**, and the guarded branch must be placed before the general `Status` branch; reversing them causes a **dominance** error. When the selector is already `Status`, using `case ON_HOLD` is usually simpler.

**Do not confuse:** `default` is not a type pattern, does not declare a variable, and does not bind an unknown enum value. The pattern variable `status` only exists within the matching guard/branch body.

## 12. Common Mistakes When Using `default` with Enums

| Mistake / Assumption | Consequence | Fix |
| --- | --- | --- |
| `default` will catch `valueOf("FUTURE")` | Parse error occurs before `switch` | Catch `IllegalArgumentException` at the parsing layer |
| `default` automatically receives `null` | In Java 17, switching on a null enum throws NPE; Java 21 needs `case null`/pre-check | Separate `null` explicitly |
| Constant `UNKNOWN` is an alias for `default` | `UNKNOWN` is just a normal constant | Write `case UNKNOWN` or an intentional parsing policy |
| `default` always returns “success” | May treat an unhandled state as success | Return a safe fallback, deny, or throw |
| Using `ordinal()` to derive stable names/IDs | Adding or reordering constants changes `ordinal` | Use explicit names or business codes |
| Using `toString()` as the default parse key | Enums may override `toString()` | Use `name()` for the declared name or a separate wire code mapping |
| Wanting the compiler to detect new enum constants while having a general `default` | Expression remains exhaustive, no prompt for dedicated handling | Consider listing all constants and omitting `default` |
| No `default` in a traditional switch statement | A constant without a case can make the statement do nothing | Add intentional fallback handling or switch to an expression |
| Using `catch (Exception)` around the entire logic | Hides other program bugs, hard to diagnose | Only catch expected parse errors at the right boundary |
| Logging raw tokens without control | Easy to spam, may contain control characters or sensitive info | Limit, sanitize, or use structured logging |
| Using a switch expression where a block branch does not `yield` | Compile error due to missing value | Use `yield` or `throw` |
| Merging new enum constants with string input errors | Fails to distinguish model evolution from bad data | Use results with distinct error codes/result types |

### Why Not Compare `ordinal`?

For example:

```java
// Do not use ordinal for protocols / persistence:
int code = Status.ON_HOLD.ordinal();
```

`ordinal()` returns the declaration position (starting at 0), not a stable business code. Inserting a constant in the middle of an enum or reordering names changes that number, causing previously stored data to be misinterpreted. When communicating outside the system, use an explicit code field and a dedicated parser if evolutionary compatibility is needed.

## 13. Testing `default` by Scenario

For `EnumDefault17` in Section 4, test these cases:

| Input | Branch or Stage | Result |
| --- | --- | --- |
| `Status.NEW` | `case NEW` | `new` |
| `Status.RUNNING` | `case RUNNING` | `running` |
| `Status.DONE` | `case DONE` | `done` |
| `Status.ON_HOLD` | `default` (valid constant without a case) | `unhandled:ON_HOLD` |
| `null` passed to `display` | Pre-check before switch | `missing` |
| `" done "` passed to `fromWire` | Parsed to `DONE`, then case | `done` |
| `"FUTURE"` passed to `fromWire` | `valueOf` throws IAE, caught | `invalid-token:FUTURE` |
| `null` passed to `fromWire` | Token pre-check | `missing-token` |

For `EnumDefault21`, additionally test:

| Input | Path | Result |
| --- | --- | --- |
| `describe(null)` | Outer switch `case null` | `input-null` |
| `describe(State.READY)` | Type pattern `State`, then `case READY` | `ready` |
| `describe(State.WAITING)` | Type pattern `State`, then enum `default` | `unmapped:WAITING` |
| `describe("FUTURE")` | Type pattern `String`, no parsing | `raw:FUTURE` |
| `describe(42)` | `switch(Object)` `default` | `unsupported` |

Beyond function outputs, test the **behavioral policy**:

1. If the fallback is fail-fast, verify the exception and message match the unsupported state.
2. If the fallback is fail-closed, verify that new/unrecognized constants are **not granted permission**.
3. If you want the compiler to enforce handling every constant, temporarily add a constant, recompile, and check where cases are missing.
4. If the application loads the enum from another module, run integration builds/tests when updating the enum or library version.
5. For external data parsing, test unfamiliar names, blank strings, whitespace, wrong casing, null, valid names, and oversized data.

Do not treat “has `default`, does not throw” as sufficient QA proof. **Correct business outcomes** determine whether a fallback is appropriate.

## 14. Practice Exercises

**Exercise 1 — Unhandled constant:** Declare `enum Shipping { CREATED, PACKING, SHIPPED, RETURNED }`. Use a `switch expression` to handle the first three states, and have `RETURNED` enter `default` and return `"unhandled:RETURNED"`. Verify the output by running it.

**Exercise 2 — Separate parsing from `switch`:** Given the string `"delayed"` which is not in `Shipping`, write `parseShipping(String)` returning a result that distinguishes `missing input` and `invalid token`. Explain why `default` in `switch` cannot catch parse errors.

**Exercise 3 — Exhaustiveness:** Write a `switch expression` with all four `case`s for `Shipping`, without `default`. Then add `CANCELLED` to the enum, recompile, and fix the missing-branch error.

**Exercise 4 — Strict policy:** With `enum PaymentState { NEW, PAID, FAILED, REFUNDED }`, only handle `NEW`, `PAID`, `FAILED` in state transitions. Use `default -> throw new IllegalStateException(...)` for `REFUNDED` when the feature is not yet supported. Write a unit test confirming it does not return a false success.

**Exercise 5 — Fail-closed:** Use the role enum `ADMIN, USER, GUEST, UNKNOWN`. Only `ADMIN` is allowed to perform deletion. Write a `switch expression` with `default -> false`, testing `UNKNOWN` and `null`. Then add `AUDITOR` and verify it is not unintentionally granted permission.

**Exercise 6 — Java 21 and `null`:** Rewrite `display(Status)` using `case null -> ...`, without a separate pre-check. Explain the difference between `case null` and `default` when the enum gains a new constant.

**Exercise 7 — Pattern `switch(Object)`:** Write `switch (Object input)` with `case Status state`, `case String raw`, `case null`, and `default`. Point out which `default` catches unlisted constants in the enum, which `default` catches unsupported object types, and which branch handles strings from an API.

**Exercise 8 — Version compatibility:** Suppose module A contains the enum and module B contains the `switch`. Describe what needs to be done when updating module A from three constants to four constants, comparing strategies with `default` and without `default` when recompiling module B.

### Self-Check Questions

- Why can `default` not receive a string `"NOT_IN_ENUM"` when `valueOf` has already failed?
- How does `case UNKNOWN` differ from `default` if an enum has the constant `UNKNOWN`?
- When can a `switch expression` on an enum omit `default`?
- Why can always having `default` **hide** the need to add a case when an enum evolves?
- If an enum is upgraded without recompiling the `switch` code, what can happen when a new constant appears?
- Does `null` enter `default` in Java 17 and Java 21?
- Why can a legacy enum `switch statement` without `default` do nothing, whereas a `switch expression` requires exhaustiveness?
- When should a fallback return a generic label, and when should it throw or deny?
- If a new security role appears, what default permission is safe?
- What test inputs would you use to distinguish a parse error, a constant without a case, and `null`?

You have mastered this lesson when you can **correctly classify the meanings of “unknown”**, choose an appropriate `default` policy, handle external strings at the parsing layer, recognize the impact of enum evolution, and use `switch expression`/`switch statement` appropriately for your Java version.

## 15. Official Sources

- [Java Language Specification SE 21 — `14.11 Switch Statements`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): enum case labels, exhaustiveness of enhanced switch statements, branch selection, and `null` handling.
- [Java Language Specification SE 21 — `15.28 Switch Expressions`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): exhaustiveness of switch expressions, value-returning branches, and `MatchException` when no label applies.
- [Oracle Java SE 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): guide to switch expressions and handling enum cases.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): `->`, `yield`, and exhaustiveness of switch expressions.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `case null`, type patterns, and extended switch rules in Java 21.
- [Java SE 21 API — Enum.valueOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)): looking up a constant by name and errors when it does not exist.

**Remember:** `default` is a **fallback branch for values that have already entered the switch**, not a decoder for external data. A good fallback must clearly express the behavior for constants without a case: **display safely, deny, or intentionally report an error**. When an enum belongs to a closed business contract and every constant needs dedicated handling, consider listing all cases **without `default`**, so the compiler helps detect changes.
