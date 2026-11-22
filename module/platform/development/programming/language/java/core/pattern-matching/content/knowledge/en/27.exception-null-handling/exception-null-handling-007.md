# Separating Data Errors from Control-Flow Errors with Pattern Matching (Java 21+)

## 1. Why separate the two kinds of errors?

In a command-receiving and processing flow, a request can fail because of **invalid data**, or because **the control flow does not permit that operation**. Both situations may cause the system to return "unsuccessful", but their causes and remedies are different.

For example, an application processes a payment command `Pay(orderId, cents)` and a cancellation command `Cancel(orderId)`:

- `Pay(null, 100)`: missing order ID — **data error**.
- `Pay("O1", -1)`: invalid amount — **data error**.
- `Pay("O1", 100)` when the workflow is already `CLOSED`: the data itself is valid, but **the operation is not allowed in the current state**.
- `raw = "PAY"` when the handler only accepts `Pay` or `Cancel` command objects: the message type does not belong to the expected protocol — in this example, it is treated as a **routing/control-flow error**.
- `null` as the input request: the example defines this as **missing data**; if `stage == null`, the example treats it as a **processing context error**.

This is **the classification policy of the illustrative domain**, not a default set of Java rules. In a public API, a message of the wrong type might be classified as a caller data error; in an internal flow, it might be a routing error. What matters is **choosing a clear, consistent policy**, rather than letting the outcome accidentally depend on `ClassCastException`, `NullPointerException`, or an overly broad `default` branch.

Pattern matching is well suited for expressing different paths using a `switch` with specific patterns, `when` guards, and clearly typed results.

## 2. Three classification layers to distinguish

To avoid mixing situations that require different handling, it helps to look at at least three layers:

| Layer | Example | Nature | Typically reasonable response |
| --- | --- | --- | --- |
| Data error (*DataProblem*) | `orderId` null/blank, `cents <= 0` | Payload violates contract | Return a validation error, specifying the field; caller fixes the data |
| Control-flow error (*FlowProblem*) | Payment in `CLOSED` state, unsupported internal command type | Operation or route does not match state/protocol | Reject the operation, check the call flow or state transition |
| Programming/infrastructure error | Unexpected `NullPointerException`, misconfiguration, I/O failure | Bug or failing system dependency | Log, diagnose, handle at an appropriate boundary; do not disguise as validation |

This article focuses on **the two expected business outcome types**, but they must be distinguished from **unexpected exceptions**. You should not catch every `RuntimeException` and return "invalid data": doing so hides programming bugs and makes it difficult for operations to identify the real root cause.

A system may also use a separate result type for infrastructure or propagate exceptions to a centralized handler. That decision depends on the architecture; do not force everything into `DataProblem` or `FlowProblem`.

## 3. Anti-pattern: using exceptions to decide data errors

A common example:

~~~java
// INTENTIONALLY DISCOURAGED:
static String bad(Object raw) {
    try {
        Pay pay = (Pay) raw;
        return pay.orderId().toUpperCase();
    } catch (RuntimeException ex) {
        return "INVALID_DATA";
    }
}
~~~

This is an **illustrative snippet** assuming `Pay` is already declared, not a standalone program. It conflates several unrelated causes:

- `raw` is not a `Pay`: may throw `ClassCastException`.
- `raw == null`: casting a null reference does not turn null into an object; calling `pay.orderId()` causes `NullPointerException`.
- `orderId == null`: `orderId().toUpperCase()` causes `NullPointerException`.
- Any other unexpected programming bug that is also a `RuntimeException` gets turned into `"INVALID_DATA"`.

Not every exception is invalid input. Instead of inferring the error category from a broad catch, **check the data structure with patterns**, **check values with guards**, and then **check control state** at the appropriate step.

The recommended approach does not completely reject using exceptions. Exceptions still have their place for programming bugs, serious invariant violations, or infrastructure failures. The issue is **not using a blanket catch as a business classifier**.

## 4. Data model and outcome model

Define the two command types:

~~~java
sealed interface Command permits Pay, Cancel {}

record Pay(String orderId, int cents) implements Command {}
record Cancel(String orderId) implements Command {}

enum Stage { OPEN, CLOSED }
~~~

These are **illustrative declarations** that will be placed together in the `ErrorSeparationDemo` class in section 9.

We choose a `sealed interface` because the illustrative system has exactly two protocol-valid commands: `Pay` and `Cancel`. Each record carries its own data. The fact that a record is `Pay` **does not mean its payload is valid**: `Pay(null, -1)` can still be constructed because the input records in the example **intentionally do not validate in their constructors** so that the handler can classify data errors.

Choose an outcome type with three explicit variants:

~~~java
sealed interface Outcome permits Done, DataProblem, FlowProblem {}

record Done(String message) implements Outcome {}
record DataProblem(String field, String reason) implements Outcome {}
record FlowProblem(String reason) implements Outcome {}
~~~

This structure lets calling code distinguish the three cases by **type**, rather than parsing a free-form message string.

- `Done`: the operation is valid and accepted.
- `DataProblem`: data is missing or fails validation; preserves the field name and reason.
- `FlowProblem`: invalid state or processing protocol; preserves the reason.

In a real system, you can add stable error codes (`enum ErrorCode`) and client-facing data, avoiding direct reliance on natural-language strings.

## 5. First step: check structure with record patterns

With a static input type of `Object`, traditional code often uses multiple `if` statements and casts. Java 21 allows deconstructing the payload directly inside `switch`:

~~~java
return switch (raw) {
    case Pay(var orderId, var cents) -> /* handle Pay */;
    case Cancel(var orderId) -> /* handle Cancel */;
    case null -> /* missing request */;
    default -> /* other command type */;
};
~~~

This is an **illustrative skeleton** (comments stand in for result expressions, so it cannot compile as-is). In the complete program in section 9, each branch returns a concrete `Outcome`.

Why is this structure useful?

1. `case Pay(...)` indicates the branch only handles a `Pay` and extracts `orderId` and `cents` without casting.
2. `case Cancel(...)` handles the cancellation command's payload according to its own structure.
3. `case null` has a different meaning from `default`. In a Java 21 pattern `switch`, **`default` does not automatically handle a null selector**; omitting a null branch or a prior check can cause the `switch` to throw `NullPointerException`.
4. `default` here represents **a message type outside the protocol**. This is an intentional classification decision; in interfaces that receive external data, the team must decide whether it is a validation error or a routing error.

**Be careful:** the variable created by `var orderId` has static type `String` but can still hold `null`. A record pattern **does not replace** non-null checks and business rules.

## 6. Second step: check data errors first

Define a concise validation helper:

~~~java
static boolean blank(String value) {
    return value == null || value.isBlank();
}
~~~

`||` evaluates from left to right. When `value == null` is true, Java does not call `value.isBlank()`, thus avoiding `NullPointerException`.

When handling payments, data branches come before control-flow branches:

~~~java
case Pay(var id, var cents) when blank(id) ->
        new DataProblem("orderId", "missing");

case Pay(var id, var cents) when cents <= 0 ->
        new DataProblem("cents", "must be positive");
~~~

These two guards describe **invalid data** without creating exceptions. A `Pay` with a blank `orderId` is rejected with field `orderId`; a command with `cents <= 0` is rejected with field `cents`.

For `Cancel`:

~~~java
case Cancel(var id) when blank(id) ->
        new DataProblem("orderId", "missing");
~~~

These are **illustrative branches** inside the `switch` in section 9, not standalone Java statements.

### Why must validation come before state checks?

Suppose the command `Pay(" ", 0)` arrives when the stage is already `CLOSED`. Both the data and the stage are invalid. This example chooses to **prioritize reporting data errors first** so the caller knows the payload is wrong, before evaluating whether the operation is valid in the processing context.

There is no single priority order that is right for every product. A security-sensitive system might intentionally check permissions or state before revealing validation details; the priority rules must be designed according to the API contract and security requirements. What you must avoid is accidentally changing the order while refactoring `case` branches and causing the same input to return a different error.

## 7. Third step: check control-flow state

Only after the payload has passed the data conditions should you evaluate whether the operation can execute:

~~~java
case Pay(var id, var cents) when stage == Stage.CLOSED ->
        new FlowProblem("payment blocked in CLOSED");

case Pay(var id, var cents) ->
        new Done("paid:" + id + ":" + cents);

case Cancel(var id) when stage == Stage.CLOSED ->
        new FlowProblem("cancel blocked in CLOSED");

case Cancel(var id) ->
        new Done("cancelled:" + id);
~~~

The order of branches is part of the logic:

- Specific `when` branches for validation must come before broader branches of the same command type.
- After validation, the `CLOSED` stage is classified as **execution not permitted**.
- The unguarded `Pay(...)` or `Cancel(...)` branch at the end is the **success** path after the preceding conditions have ruled out failure cases.

If you place an unguarded `case Pay(...)` branch before `Pay(...) when ...` branches, the compiler may report the later specific branches as *dominated*. Ordering from **specific first, general last** lets Java verify the patterns and helps readers follow the decision logic.

### Control-flow errors and programming bugs are not necessarily the same

A payment command in the `CLOSED` state may be an expected business response (*conflict*), so the example returns `FlowProblem`. However, if code enters a state that **should be impossible according to internal invariants**, that may be a bug and warrants throwing `IllegalStateException` or reporting an internal error rather than treating it as a normal business rejection.

Similarly, `stage == null` in the example is classified as `FlowProblem("stage missing")` because it is a required context supplied by the caller. Another application might treat that as a programming error and use `Objects.requireNonNull(stage)`. **What matters is clarifying where the value comes from and who is responsible for fixing it**.

## 8. Separating outcomes from exceptions and keeping switches exhaustive

A consumer of the outcome can use a `switch expression` on `Outcome`:

~~~java
static String describe(Outcome outcome) {
    return switch (outcome) {
        case Done(var message) -> "OK:" + message;
        case DataProblem(var field, var reason) ->
                "DATA:" + field + ":" + reason;
        case FlowProblem(var reason) -> "FLOW:" + reason;
    };
}
~~~

Because `Outcome` is a `sealed interface` and all three subtypes are records (final), the compiler can verify that the three branches cover all permitted **non-null** subtypes. No `default` is needed in the example. If a new subtype is added, the expression will require updating the branches, helping catch forgotten outcome types.

The method above treats `outcome` as non-null by contract. If a caller passes null, it does not automatically become a `DataProblem`; the application should decide whether to reject null at this boundary. Avoid using type exhaustiveness as an excuse to forget about nullability.

Another method can classify the valid command set:

~~~java
static String kind(Command command) {
    java.util.Objects.requireNonNull(command, "command");

    return switch (command) {
        case Pay pay -> "PAY";
        case Cancel cancel -> "CANCEL";
    };
}
~~~

Unlike `handle(Object raw, Stage stage)` at the entry boundary, `kind(Command)` only accepts a **type-valid** `Command`, so it does not need a `default` branch to catch strings or integers. This difference reflects an architectural decision: **check types and data at the boundary**, then pass stronger types into the domain.

## 9. Complete Java 21 program, 19 test cases

Save the code below in **`ErrorSeparationDemo.java`**. The program requires no libraries outside the JDK.

~~~java
public class ErrorSeparationDemo {
    sealed interface Command permits Pay, Cancel {}
    record Pay(String orderId, int cents) implements Command {}
    record Cancel(String orderId) implements Command {}
    enum Stage { OPEN, CLOSED }

    sealed interface Outcome permits Done, DataProblem, FlowProblem {}
    record Done(String message) implements Outcome {}
    record DataProblem(String field, String reason) implements Outcome {}
    record FlowProblem(String reason) implements Outcome {}

    private static int passed = 0;

    static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    static Outcome handle(Object raw, Stage stage) {
        if (stage == null) {
            return new FlowProblem("stage missing");
        }

        return switch (raw) {
            case null -> new DataProblem("request", "missing");

            case Pay(var id, var cents) when blank(id) ->
                new DataProblem("orderId", "missing");
            case Pay(var id, var cents) when cents <= 0 ->
                new DataProblem("cents", "must be positive");
            case Pay(var id, var cents) when stage == Stage.CLOSED ->
                new FlowProblem("payment blocked in CLOSED");
            case Pay(var id, var cents) ->
                new Done("paid:" + id + ":" + cents);

            case Cancel(var id) when blank(id) ->
                new DataProblem("orderId", "missing");
            case Cancel(var id) when stage == Stage.CLOSED ->
                new FlowProblem("cancel blocked in CLOSED");
            case Cancel(var id) ->
                new Done("cancelled:" + id);

            default -> new FlowProblem("unsupported command type");
        };
    }

    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Done(var message) -> "OK:" + message;
            case DataProblem(var field, var reason) ->
                "DATA:" + field + ":" + reason;
            case FlowProblem(var reason) -> "FLOW:" + reason;
        };
    }

    static String kind(Command command) {
        java.util.Objects.requireNonNull(command, "command");
        return switch (command) {
            case Pay pay -> "PAY";
            case Cancel cancel -> "CANCEL";
        };
    }

    static void check(
            String label, Object raw, Stage stage, Outcome expected) {
        Outcome actual = handle(raw, stage);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected + ", actual " + actual);
        }
        passed++;
        System.out.println("PASS " + label + " -> " + describe(actual));
    }

    static void checkKind(
            String label, Command command, String expected) {
        String actual = kind(command);
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": " + actual);
        }
        passed++;
        System.out.println("PASS " + label + " -> " + actual);
    }

    public static void main(String[] args) {
        check("pay-ok", new Pay("O1", 120), Stage.OPEN,
                new Done("paid:O1:120"));
        check("cancel-ok", new Cancel("O1"), Stage.OPEN,
                new Done("cancelled:O1"));
        check("missing-request", null, Stage.OPEN,
                new DataProblem("request", "missing"));
        check("missing-stage", new Pay("O1", 120), null,
                new FlowProblem("stage missing"));

        check("pay-null-id", new Pay(null, 120), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("pay-blank-id", new Pay("  ", 120), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("pay-zero", new Pay("O1", 0), Stage.OPEN,
                new DataProblem("cents", "must be positive"));
        check("pay-negative", new Pay("O1", -1), Stage.OPEN,
                new DataProblem("cents", "must be positive"));
        check("data-before-stage", new Pay(" ", 0), Stage.CLOSED,
                new DataProblem("orderId", "missing"));
        check("pay-closed", new Pay("O1", 120), Stage.CLOSED,
                new FlowProblem("payment blocked in CLOSED"));

        check("cancel-null-id", new Cancel(null), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("cancel-blank-id", new Cancel(" "), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("cancel-closed", new Cancel("O1"), Stage.CLOSED,
                new FlowProblem("cancel blocked in CLOSED"));
        check("unsupported-string", "PAY", Stage.OPEN,
                new FlowProblem("unsupported command type"));
        check("unsupported-integer", 7, Stage.OPEN,
                new FlowProblem("unsupported command type"));
        check("pay-min-positive", new Pay("O2", 1), Stage.OPEN,
                new Done("paid:O2:1"));
        check("cancel-missing-stage", new Cancel("O1"), null,
                new FlowProblem("stage missing"));
        checkKind("sealed-pay", new Pay("O1", 1), "PAY");
        checkKind("sealed-cancel", new Cancel("O1"), "CANCEL");

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Compile and run on JDK 21 or later:

~~~bash
javac --release 21 ErrorSeparationDemo.java
java ErrorSeparationDemo
~~~

**Expected output:**

~~~text
PASS pay-ok -> OK:paid:O1:120
PASS cancel-ok -> OK:cancelled:O1
PASS missing-request -> DATA:request:missing
PASS missing-stage -> FLOW:stage missing
PASS pay-null-id -> DATA:orderId:missing
PASS pay-blank-id -> DATA:orderId:missing
PASS pay-zero -> DATA:cents:must be positive
PASS pay-negative -> DATA:cents:must be positive
PASS data-before-stage -> DATA:orderId:missing
PASS pay-closed -> FLOW:payment blocked in CLOSED
PASS cancel-null-id -> DATA:orderId:missing
PASS cancel-blank-id -> DATA:orderId:missing
PASS cancel-closed -> FLOW:cancel blocked in CLOSED
PASS unsupported-string -> FLOW:unsupported command type
PASS unsupported-integer -> FLOW:unsupported command type
PASS pay-min-positive -> OK:paid:O2:1
PASS cancel-missing-stage -> FLOW:stage missing
PASS sealed-pay -> PAY
PASS sealed-cancel -> CANCEL
ALL PASSED: 19
~~~

### Reading the test results

- **`pay-ok`, `cancel-ok`, `pay-min-positive`** verify the success flow and the boundary value `cents == 1`.
- **`missing-request`** confirms `case null` returns a data error instead of causing an NPE.
- **`pay-null-id`, `pay-blank-id`, `pay-zero`, `pay-negative`, and the missing-ID `cancel` cases** confirm that validation returns `DataProblem`.
- **`data-before-stage`** confirms the **data-error-first** policy when a payload both lacks an ID and hits the `CLOSED` stage. The `orderId` check branch appears before the stage branch.
- **`pay-closed` and `cancel-closed`** return `FlowProblem` when the payload is valid but the operation is not allowed in the current state.
- **`missing-stage`, `cancel-missing-stage`** return `FlowProblem` because the control context is not provided.
- **`unsupported-string` and `unsupported-integer`** confirm that command types outside the allowed set fall into `default`, per the example's classification policy.
- **`sealed-pay` and `sealed-cancel`** demonstrate an exhaustive `switch` on `Command` handling both subtypes directly without a `default`.

The `check` method compares the **actual outcome object** using the record's `equals`, rather than checking only part of a display string. If the result is wrong, it throws `AssertionError` immediately. Therefore, `ALL PASSED: 19` only appears after every case is verified.

This is a **classification and result-returning** model; the code does not actually call a payment service or mutate order state. When integrating into a real system, side-effecting actions must be executed in the appropriate application layer with separate handling for infrastructure failures.

## 10. From the illustration to real-world architecture

A workflow typically has these steps:

1. **Receive data at the boundary** (HTTP, message queue, CLI, file). This is where data may be missing fields, have the wrong type, wrong format, or be null.
2. **Parse and validate** to turn untrusted data into valid objects. Record data errors using a specific structure such as `DataProblem(field, code)`.
3. **Check execution preconditions** such as order state, permissions, and flow rules. Return an appropriate business response if the operation is not yet permitted.
4. **Execute the behavior** once all conditions are met; in systems with state/concurrency, protect consistency when mutating state.
5. **Map the outcome to the external protocol**: e.g., API response, message, or log. Distinguish validation errors, business conflicts, and system errors.

Pattern matching is useful at **type-branching points**, but you should avoid turning a `switch` into the place where all business logic is executed. If validation or state-transition checks are complex, extract them into clearly named methods so each `case` branch expresses intent rather than containing dozens of expressions.

### Mapping to an API is an application decision

For example, in an HTTP API, `DataProblem` might map to a 400 or 422 response depending on the contract; `FlowProblem` due to a disallowed state might map to 409, 403, or a domain-specific response. **There is no mandatory HTTP mapping imposed by Java pattern matching**. An infrastructure failure or bug should not be returned as 400 just because it landed in the same `catch` as data errors.

You should log diagnostic details for control-flow/infrastructure errors, without exposing stack traces or sensitive system details in user-facing messages.

## 11. Exceptions still have a role, but at the right layer

There is no rule that "every error must be a result record." Distinguish between:

- **Anticipated validation**: use `DataProblem` or a structured business error type that helps the caller fix the input; a dedicated validation exception can also be used if that is the project's consistent contract.
- **Operation invalid for the current state**: use `FlowProblem`, conflict, or a domain exception per the protocol, rather than mixing it into a data format error.
- **Bugs and broken internal invariants**: `IllegalStateException` or an appropriate exception may be used and recorded by centralized error handling. Do not turn it into `DataProblem` and let the system silently ignore a bug.
- **I/O, timeout, database, network errors**: classify at the infrastructure layer, with retry/circuit-breaker/observability strategies as appropriate. Do not infer an invalid payload merely from a connection failure.
- **Unexpected `NullPointerException`**: usually a sign of a code path missing a null contract or violating an invariant. Do not catch all of them and return "missing data" without verifying that the null actually came from the request.

Anti-pattern example in the processing layer:

~~~java
try {
    // Process, call services, manipulate objects ...
} catch (Exception ex) {
    // WRONG: every kind of error is treated as an invalid payload.
    return new DataProblem("request", "invalid");
}
~~~

This is **illustrative pseudocode**; it cannot compile standalone due to missing method context. It hides control-flow errors, bugs, and infrastructure failures alike. Instead, validate data intentionally; catch only **the exceptions this layer actually knows how to handle**, so unexpected exceptions are recorded at the proper layer.

## 12. Common pitfalls when combining patterns with error classification

**Pitfall 1 — using `default` to swallow all errors.** In a `switch` over `Object`, `default` can receive unsupported command types, but it is not a catch-all for exceptions and does not automatically handle a null selector. Include `case null` or a separate null check.

**Pitfall 2 — lumping missing fields, invalid state, and system errors into the same "invalid" message.** Callers will not know whether to fix the payload or change their action. Create distinct outcome types and clear error codes.

**Pitfall 3 — placing a success branch before a guarded branch.** A broad `case Pay(...)` before `case Pay(...) when ...` can shadow validation branches and cause dominated errors or unreachable logic.

**Pitfall 4 — assuming `var` is non-null.** `case Pay(var id, ...)` can produce `id == null`. The `blank(id)` helper in the example handles both null and blank strings.

**Pitfall 5 — treating every wrong message type as a flow error.** The example does so because it models an internal protocol. In an API accepting raw JSON, a wrong request type might be a data error. Define the boundary and contract before mapping error categories.

**Pitfall 6 — turning `IllegalStateException` into `DataProblem` in a broad catch.** An internal invariant violation may be a serious bug; users should not be led to think they omitted a field.

**Pitfall 7 — mixing error priority order without tests.** For inputs with both an invalid payload and an invalid state, the earlier branch decides the result. Multi-error tests make the priority policy explicit.

**Pitfall 8 — using exceptions as normal validation flow.** Not always wrong, but it can make code hard to follow when try/catch blocks sprawl. For expected, common input errors, a typed result is usually easier to test and operate.

**Pitfall 9 — assuming `sealed` validates field values.** `sealed Command` restricts subtypes, but does not prevent `Pay(null, -1)`. Constructors, factories, or validation steps must enforce data invariants.

**Pitfall 10 — forgetting to update logic when adding a subtype.** With an exhaustive `switch` without `default`, the compiler helps catch missing branches. However, a `switch` on `Object` with a broad `default` may silently accept the new subtype as unsupported. When extending the protocol, test the input boundary as well.

## 13. Code review checklist and exercises

### Checklist

1. Does the code distinguish **invalid payload**, **state-disallowed operation/route**, and **unexpected errors**?
2. Is a `null` selector handled by contract rather than accidentally throwing NPE?
3. Are fields extracted via `var` or record patterns checked for null before dereferencing?
4. Do data-checking `when` branches appear before general success branches?
5. When multiple conditions fail at once, is **error priority order** defined and tested?
6. Is there an overly broad catch that accidentally turns bugs and network failures into data errors?
7. Do outcomes have explicit types that can be distinguished without parsing message strings?
8. Are "unsupported type" cases classified according to the proper boundary (public API vs. internal protocol)?
9. Is the `sealed` subtype set updated when adding new variants, and are exhaustive `switch` statements checked?
10. Are there tests for null, blank strings, boundary numbers, disallowed states, other command types, and simultaneous errors?

### Exercises

- Add a `Refund(String orderId, int cents)` subtype to `Command`. Observe which branch in `kind(Command)` needs updating to remain exhaustive, and decide how `handle(Object, Stage)` would treat it before adding the `Refund` branch.
- Change the policy to **check stage before validation** for `Pay`. Update the `data-before-stage` test to the new expected result and explain the impact on the error information the caller receives.
- Add `DataProblem("orderId", "too long")` when the order ID is longer than 20 characters. Where should the guard be placed so `length()` is not called on null?
- Try passing `null` to `kind(Command)`; compare explicit rejection via `Objects.requireNonNull` with `case null` when you want to treat null as a business outcome.
- Write an adapter that returns distinct error codes for `DataProblem`, `FlowProblem`, and unexpected exceptions, without creating a generic `catch (Exception)` that turns everything into validation.

**Key takeaway:** Pattern matching helps identify **what kind of command this is**, guards confirm **whether the data is valid**, and state conditions answer **whether the command is allowed to run right now**. Represent failure reasons with distinct result types, keep check ordering intentional, and do not hide programming or infrastructure errors behind an overly broad catch.