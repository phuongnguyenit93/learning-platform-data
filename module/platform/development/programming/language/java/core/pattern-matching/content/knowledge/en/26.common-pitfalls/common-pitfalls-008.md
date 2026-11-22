# Mixing Business Logic into Guards: A Common Pitfall in Java Pattern Matching

When using **pattern matching for `switch`**, Java allows placing a Boolean expression after the **`when`** keyword to check an additional condition right at the `case` branch. This is a useful feature, but it can also easily lead to a design mistake: **putting too much business logic, especially operations with side effects, into a guard**. As a result, a branch that looks like a simple check can end up mutating data, calling external services, creating transactions, or throwing hard-to-trace exceptions.

This lesson belongs to **Java Core Pattern Matching → Common Pitfalls**. The goal is to understand exactly how `when` works, distinguish **pure business conditions** from **business actions**, know when to use a helper predicate, when to separate validation, and when to move business logic out of the guard so that code remains clear and easy to test.

**Version scope:** Pattern matching for `switch` was finalized in **Java 21** (JEP 441), and record patterns were also finalized in Java 21 (JEP 440). The complete examples run on **JDK 21 and later** without needing to enable preview features.

## 1. What is the role of a `when` guard?

A `case` with a pattern checks the type or structure of the selector. A **guard** checks an additional condition after the pattern has matched:

~~~java
// Java 21+ snippet; 'value' is an already-declared Object.
String result = switch (value) {
    case Integer number when number > 0 -> "Positive: " + number;
    case Integer number -> "Non-positive: " + number;
    case null -> "Missing";
    default -> "Other type";
};
~~~

How to read this from top to bottom:

1. If `value` is a non-`null` `Integer`, Java binds it to the pattern variable `number`.
2. Only after the type pattern **matches** does Java evaluate the guard `number > 0`.
3. If the guard is true, the `"Positive"` branch is selected. If the guard is false, **no branch is selected yet**; Java continues checking subsequent matching cases.
4. Therefore, `Integer.valueOf(0)` and negative numbers are handled by the unguarded `case Integer number` branch.
5. `case null` handles a `null` selector; `default` handles all remaining types.

A guard returns a **`boolean`**. It is not an event handler block, not a transaction boundary, and does not automatically manage retries or rollbacks.

### Is it allowed to call methods in a guard?

Yes. The following syntax is **valid** if `isEligible(...)` returns `boolean`:

~~~java
// Illustrative snippet: isEligible is a pure check method.
case OrderSubmitted(var orderId, var units)
        when isEligible(orderId, units) -> ...
~~~

Java **does not require** a method in a guard to be pure. However, as a matter of design, you should ensure a guard only checks a condition and does not itself trigger hard-to-reverse actions.

**Key distinction:** "Do not mix business logic into guards" **does not mean forbidding all business-meaningful conditions**. For example, `when amountCents > 0`, `when quantity >= 100`, or `when isVip(customer)` can be reasonable if they are **pure, cheap, and easy-to-understand** checks. The problem arises when a guard turns into a place for **executing business workflows** such as charging payments, writing to a database, sending emails, updating inventory, or deciding a state sequence with multiple failure reasons.

## 2. Why are business actions in guards dangerous?

Consider a style you intentionally **should not use**:

~~~java
// ANTI-PATTERN, illustrative only, not a standalone program.
// 'paymentGateway' and 'order' are hypothetical dependencies.
String result = switch (order) {
    case PayOrder(var id, var amount)
            when paymentGateway.charge(id, amount) -> "Payment accepted";
    case PayOrder(var id, var amount) -> "Payment not accepted";
    default -> "Unsupported";
};
~~~

At first glance, the guard seems to simply check "can it be paid?". However, `charge(...)` is usually an **action that sends a payment capture request**, not a predicate. When the `case` is evaluated, the method may already call an external service **before** the branch is selected.

Specific risks:

- **Side effects even when the guard returns `false`:** a request or write operation may have already executed before Java moves to the next case.
- **No automatic rollback:** `switch` has no knowledge that a charge, audit write, or inventory change occurred; it does not undo them if the guard evaluates to false.
- **Hard-to-follow execution flow:** looking at `case ... when ...`, a maintainer may not realize I/O operations are happening right inside the condition.
- **Hard to test:** testing which branch is selected requires mocking a payment gateway, database, clock, or message broker.
- **Case order becomes service call order:** reordering guards for a syntactic refactor can alter the order of actions in the system.
- **An exception does not mean the guard is false:** when a helper throws an exception, branch selection does not simply "fall through to the next case."
- **Retries and repeated checks:** when the enclosing method is retried or a guard appears in multiple execution paths, side effects may execute multiple times. You should never rely on a guard "being called only once for the entire business operation."

Rule of thumb: **the guard should decide which branch applies; the branch body or a dedicated service should perform the business action**.

## 3. Understanding exactly when a guard is false, true, or throws an exception

With Java 21+:

~~~java
// Illustrative snippet, 'input' is Object.
String message = switch (input) {
    case String text when text.isBlank() -> "Blank text";
    case String text -> "Text: " + text;
    case null -> "No text";
    default -> "Different type";
};
~~~

- If the selector is `"   "`, the type pattern matches and the guard is true: `"Blank text"` is selected.
- If the selector is `"hello"`, the type pattern matches but the guard is false: evaluation continues to `case String text`, selecting `"Text: hello"`.
- If the selector is an `Integer`, the `String` type pattern does not match: the guards of both `String` cases **do not run**.
- If the selector is `null`, the type patterns do not match; the `case null` branch handles it.

Crucially: **a guard is not a `try/catch` block**. If you write:

~~~java
// Illustrates a guard that may throw an exception.
case String text when parseRemotePolicy(text) -> "Allowed";
~~~

and `parseRemotePolicy(text)` throws an exception, the `switch` **completes abruptly** by propagating the exception, unless the exception is handled inside the call or outside the `switch`. It does **not** treat the guard as `false` by default to pick a later case.

If a policy lookup can fail due to network or I/O, perform that step **outside the classification**, handle errors explicitly, and pass only the resolved result into the decision.

## 4. Demonstrating guard side effects with runnable code

The following example intentionally creates an **impure** guard to observe the mechanism. It does not access the network or a database; the side effect is simply incrementing a counter.

Create the file **`SideEffectGuardDemo.java`**:

~~~java
public class SideEffectGuardDemo {
    private static int calls;

    static boolean badCheck(int number) {
        calls++;                 // Side effect: mutates state.
        return number > 0;
    }

    static String route(Object input) {
        return switch (input) {
            case Integer number when badCheck(number) -> "positive";
            case Integer number -> "not positive";
            case null -> "missing";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(-2));
        System.out.println("Calls: " + calls);
        System.out.println(route(4));
        System.out.println("Calls: " + calls);
    }
}
~~~

Compile and run with JDK 21+:

~~~bash
javac --release 21 SideEffectGuardDemo.java
java SideEffectGuardDemo
~~~

Output:

~~~text
not positive
Calls: 1
positive
Calls: 2
~~~

Analysis:

1. On the first call, `input` is `-2`, which is autoboxed to `Integer` when passed as `Object`. The pattern `Integer number` matches.
2. Java calls `badCheck(-2)`. The `calls` counter **increments from 0 to 1**, then the method returns `false`.
3. Because the guard is false, the `"positive"` branch is not selected. The subsequent `case Integer number` branch returns `"not positive"`, **yet the guard's side effect still remains**.
4. On the next call, `badCheck(4)` increments the counter to 2 and returns `true`. The first branch is selected.

This is a scaled-down version of the "charge in a guard that returns `false`" problem: the consequence has already happened even though the first branch was not chosen. `calls` is just an illustrative counter; in practice, the risk could be duplicate writes, sending erroneous notifications, or mutating external state.

**Do not fix this by hiding the side effect deeper inside a helper.** Renaming `badCheck` to `isAllowed` does not make it pure if it still writes data internally.

## 5. What kind of conditions should a guard contain?

An **appropriate** guard typically has these characteristics:

- **Pure:** for the same unchanged inputs, evaluating the check causes no external state updates.
- **Clear intent:** a reader looking at the condition immediately understands why the branch is selected.
- **Cheap with predictable runtime:** no network calls, database queries, or waiting on external resources.
- **`null`-safe:** checks for `null` before invoking methods on potentially null components.
- **Independent of side-effect ordering across cases.**

Appropriate example:

~~~java
// Java 21+ snippet: records are declared accordingly.
case Submitted(var id, var units, var priceCents)
        when id != null && !id.isBlank()
             && units > 0 && priceCents > 0 ->
        "Valid submission";
~~~

Checking the order ID, unit count, and unit price are all **pure** checks. Using a guard for basic valid/invalid classification is reasonable, provided there is a branch handling data that does not pass the guard.

Example **worth reconsidering**:

~~~java
// ANTI-PATTERN: illustrative, not standalone code.
case Submitted(var id, var units, var priceCents)
        when checkQuota(id)
             && reserveInventory(id, units)
             && writeAuditLog(id)
             && notifyWarehouse(id) ->
        "Accepted";
~~~

Even though all the helpers above may return `boolean`, placing them in `when` ties the business flow and side effects to the **short-circuit evaluation order of the conditional expression**. If `reserveInventory` succeeds but `notifyWarehouse` fails, selecting the fallback branch does not mean the reserved inventory will be released.

**Redesign:** the condition should only rely on data or an explicitly computed result; state-changing steps belong in a processing flow with dedicated transaction, idempotency, and error-handling design.

### Named predicates still need internal scrutiny

If a condition starts getting long, you can extract it into a helper:

~~~java
static boolean isValidOrder(String id, int units, long unitPriceCents) {
    return id != null && !id.isBlank()
            && units > 0 && unitPriceCents > 0;
}

// Java 21+ case branch snippet.
case Submitted(var id, var units, var priceCents)
        when isValidOrder(id, units, priceCents) ->
        new Decision(DecisionType.ACCEPT_SUBMISSION, id);
~~~

A name like `isValidOrder` should only be used when the helper **only checks**. If the helper queries a database, performs writes, creates a payment, mutates a cache, or emits events, that name is misleading. Business rules that depend on unavailable data (such as current quota in another system) should generally be gathered or validated at the service layer before reaching a pure decision.

## 6. Separating three steps: check, decision, action

A readable and testable structure:

~~~text
Input / Event
      |
      v
[Check types and purely computable data]
      |
      v
[Decision]  <-- pattern + when (if appropriate)
      |
      v
[Perform action]         <-- save state, audit, I/O, notification
      |
      v
[Return result]
~~~

Not every application needs three separate layers. However, **the boundary between decision and side effects must be visible in the code**.

For example:

- `decide(event)`: takes an event and returns a `Decision`; no logging, no API calls.
- `execute(event, audit)`: calls `decide`, then **performs actions** based on the decision.
- If real processing is transactional, an outer service must manage **transactions, duplicate delivery, retries, access control, and idempotency**. `switch` does not solve those problems on its own.

The key benefit is that `Decision` can be tested with pure unit tests; the tester does not need to spin up a payment gateway or database just to verify which events are classified as valid.

## 7. Complete Java 21+ example: pure guard, separated action

Create the file **`GuardSeparationDemo.java`**:

~~~java
public class GuardSeparationDemo {
    sealed interface OrderEvent permits Submitted, CancelRequested {}

    record Submitted(String orderId, int units, long unitPriceCents)
            implements OrderEvent {}

    record CancelRequested(String orderId, String reason)
            implements OrderEvent {}

    enum DecisionType {
        ACCEPT_SUBMISSION, REJECT_SUBMISSION,
        ACCEPT_CANCELLATION, REJECT_CANCELLATION
    }

    record Decision(DecisionType type, String orderId) {}

    static boolean validOrderId(String id) {
        return id != null && !id.isBlank();
    }

    static boolean validReason(String reason) {
        return reason != null && !reason.isBlank();
    }

    static Decision decide(OrderEvent event) {
        if (event == null) {
            throw new IllegalArgumentException("event required");
        }

        return switch (event) {
            case Submitted(var id, var units, var unitPriceCents)
                    when validOrderId(id) && units > 0 && unitPriceCents > 0 ->
                    new Decision(DecisionType.ACCEPT_SUBMISSION, id);

            case Submitted(var id, var units, var unitPriceCents) ->
                    new Decision(DecisionType.REJECT_SUBMISSION, id);

            case CancelRequested(var id, var reason)
                    when validOrderId(id) && validReason(reason) ->
                    new Decision(DecisionType.ACCEPT_CANCELLATION, id);

            case CancelRequested(var id, var reason) ->
                    new Decision(DecisionType.REJECT_CANCELLATION, id);
        };
    }

    static String execute(OrderEvent event, java.util.List<String> audit) {
        Decision decision = decide(event);

        return switch (decision.type()) {
            case ACCEPT_SUBMISSION -> {
                audit.add("submitted:" + decision.orderId());
                yield "Submitted " + decision.orderId();
            }
            case REJECT_SUBMISSION -> "Rejected submission";
            case ACCEPT_CANCELLATION -> {
                audit.add("cancelled:" + decision.orderId());
                yield "Cancellation accepted " + decision.orderId();
            }
            case REJECT_CANCELLATION -> "Rejected cancellation";
        };
    }

    public static void main(String[] args) {
        var audit = new java.util.ArrayList<String>();

        System.out.println(execute(new Submitted("O-1", 3, 500), audit));
        System.out.println(execute(new Submitted("O-2", 0, 500), audit));
        System.out.println(execute(
                new CancelRequested("O-1", "customer request"), audit));
        System.out.println(execute(new CancelRequested("O-1", "  "), audit));
        System.out.println(execute(new Submitted(null, 2, 100), audit));
        System.out.println("Audit: " + audit);

        try {
            execute(null, audit);
        } catch (IllegalArgumentException ex) {
            System.out.println("Null: " + ex.getMessage());
        }
    }
}
~~~

Run with JDK 21+:

~~~bash
javac --release 21 -encoding UTF-8 GuardSeparationDemo.java
java GuardSeparationDemo
~~~

Output:

~~~text
Submitted O-1
Rejected submission
Cancellation accepted O-1
Rejected cancellation
Rejected submission
Audit: [submitted:O-1, cancelled:O-1]
Null: event required
~~~

### Reading the code by responsibility

**A. Domain types:** `sealed interface OrderEvent` models two event types. Each record holds a strongly typed payload. Constructing `Submitted(null, 2, 100)` is not prevented by the compiler itself; invariants must be checked at runtime or in the constructor according to the domain contract.

**B. `validOrderId` / `validReason`:** these are read-only predicates that do not mutate state. They are `null`-safe thanks to `&&` short-circuiting. Neither helper makes network requests or performs writes.

**C. `decide`:** `case Submitted(... ) when ...` and `case CancelRequested(...) when ...` only classify. If a guard is not satisfied, the unguarded case for the same record handles the rejected case. Both record types are exhaustively covered; the `switch` expression does not need a `default` when the selector has the sealed static type `OrderEvent` and all permits are covered.

**D. `execute`:** only after the decision is computed does `audit.add(...)` run inside the selected branch. Rejected decisions do not record an audit entry in this example. That is an illustrative choice, **not a standard audit policy for every system** — many applications still need to audit rejected requests as well, and should express the intent and timing of logging explicitly.

**E. `null`:** `decide(null)` throws `IllegalArgumentException("event required")` before running the `switch`, so `case null` is not needed inside `decide`'s `switch`. Conversely, `null` is still tested in `main` to demonstrate error reporting.

**F. Example limitations:** `CancelRequested("O-1", ...)` only checks the structure of the ID and reason. This program **does not** check whether the order exists, who owns it, or whether its current state allows cancellation. In production, a service must validate actual state before performing cancellation and coordinate with a transaction. `DecisionType.ACCEPT_CANCELLATION` in the example must not be mistaken as sufficient authorization to cancel an order in a real system.

## 8. When should you drop `when` and use a helper returning a detailed result?

A Boolean guard only answers **"true or false"**. If the system must distinguish multiple rejection reasons, cramming everything into one long condition loses information.

For example, suppose the requirements are:

- Missing order ID → `INVALID_ID`.
- Non-positive quantity → `INVALID_UNITS`.
- Invalid unit price → `INVALID_PRICE`.

In that case, you can write a **pure** helper that returns a validation result:

~~~java
// Conceptual standalone example; place in a class with appropriate declarations.
enum ValidationCode {
    OK, INVALID_ID, INVALID_UNITS, INVALID_PRICE
}

static ValidationCode validateSubmitted(
        String orderId, int units, long unitPriceCents) {
    if (orderId == null || orderId.isBlank()) {
        return ValidationCode.INVALID_ID;
    }
    if (units <= 0) {
        return ValidationCode.INVALID_UNITS;
    }
    if (unitPriceCents <= 0) {
        return ValidationCode.INVALID_PRICE;
    }
    return ValidationCode.OK;
}
~~~

Then handle the result explicitly in one branch instead of attaching three or four layers of business rules to a guard:

~~~java
// Snippet inside a switch expression returning ValidationCode.
case Submitted(var id, var units, var price) ->
        validateSubmitted(id, units, price);
~~~

Or in a dedicated method:

~~~java
// Snippet; Submitted and ValidationCode are already defined.
static ValidationCode validateEvent(Submitted event) {
    return validateSubmitted(
            event.orderId(), event.units(), event.unitPriceCents());
}
~~~

This approach is convenient for unit tests: each error type has a clear name and explicit check order. If user-friendly messages are needed, `ValidationCode` can be mapped to messages at the presentation layer. You should **not** perform data writes inside `validateSubmitted`.

### When to keep `when`?

Keep a guard when it is a **simple filter** with a clear subsequent branch:

~~~java
// Java 21+ snippet, 'input' is Object.
String size = switch (input) {
    case Integer count when count >= 100 -> "large";
    case Integer count -> "small";
    case null -> "missing";
    default -> "unsupported";
};
~~~

There is no need to create a service just to check `count >= 100`. The goal is **clarity**, not "forbidding business logic from appearing in conditions."

## 9. Guards, variable scope, and case ordering

### Pattern variables are in scope within the guard

~~~java
// Java 21+ snippet: 'input' has type Object.
String label = switch (input) {
    case String text when !text.isBlank() -> "Text: " + text;
    case String text -> "Blank text";
    case null -> "Missing";
    default -> "Other";
};
~~~

`text` is only available after the `String text` pattern has matched. The compiler tracks variable scope in both the guard and the branch body. If the pattern does not match, its corresponding guard is not evaluated.

### General cases must come after guarded cases

The following **does not compile** due to dominance:

~~~java
// INTENTIONALLY WRONG: unguarded String case before guarded branch.
String label = switch (input) {
    case String text -> "Anything String";
    case String text when text.isBlank() -> "Blank"; // Dominated.
    case null -> "Missing";
    default -> "Other";
};
~~~

Every value matching `case String text when ...` is already covered by the preceding `case String text` branch. Place **guarded cases first**, and unguarded cases of the same type after them.

Do not put a side effect in a guard just to "force this branch to be evaluated first" or "use case order as workflow execution order." Case order is for **classification**, not a substitute for intentional orchestration.

### Overlapping guard conditions

Example:

~~~java
// Snippet: 'input' has type Object.
String label = switch (input) {
    case Integer n when n >= 100 -> "at least 100";
    case Integer n when n >= 50 -> "50 to 99";
    case Integer n -> "below 50";
    case null -> "missing";
    default -> "not integer";
};
~~~

The number `120` also satisfies `n >= 50`, but it is handled by the **first matching** branch. Here that is intentional; however, if guards represent complex policies, overlapping conditions can make outcomes depend on ordering in ways maintainers overlook. In such cases, a classification helper or an explicit decision table may be better.

## 10. `null` and exceptions in guards

This is a very common source of bugs when record patterns extract reference data:

~~~java
record Customer(String name) {}

// Java 21+ snippet, 'input' is Object.
String label = switch (input) {
    case Customer(var name) when name != null && !name.isBlank() ->
            "Customer: " + name;
    case Customer(var name) -> "Missing customer name";
    case null -> "No customer";
    default -> "Other";
};
~~~

Notes:

- `Customer(var name)` matches a non-`null` `Customer`, even when **the `name` component is `null`**.
- `name != null && !name.isBlank()` ensures `isBlank()` is not called on `null`; `&&` evaluates the right-hand side only when the left-hand side is true.
- If the guard were written as `!name.isBlank()` and `name == null`, a `NullPointerException` would be thrown while evaluating the guard, and it would **not** fall through to `case Customer(var name)`.
- `case null` handles the selector `input == null`, which is different from the component `Customer.name == null`.

Similarly, if a guard calls a helper that can throw `IllegalStateException` or another unchecked exception, the caller must catch and handle the exception according to the program's contract. `switch` does not automatically treat an exception as a Boolean `false` condition.

### Can a guard read external state?

Java allows it, but you should think carefully. For example, checking the **current time**, inventory count, or a user's access permissions from a service can change between the check and the execution. Even when a guard only reads without writing, it can still introduce a **time-of-check/time-of-use (TOCTOU) problem**.

The right fix depends on the domain: take an explicit snapshot/version, re-validate within the same transaction, use optimistic locking, or perform an atomic operation in a dedicated service. Never assume that because a guard returned `true`, an external condition still holds at write time.

## 11. Cases easily confused with transactions and retries

Suppose a real workflow needs to check inventory, reserve stock, and create an order. A guard like:

~~~java
// ANTI-PATTERN: illustrative only, method names indicate side effects.
case Submitted(var id, var units, var price)
        when inventory.reserve(id, units) && payment.charge(id, price) ->
        "accepted";
~~~

causes `inventory.reserve` to run before `payment.charge`. If the first action succeeds but the second returns `false`, `switch` selects another branch, yet the inventory reservation **may still persist**. If the method is retried after a timeout, there is a risk of duplicate operations.

Better yet, business workflows should be expressed in an **application service** with explicit ordering, transactions, and retry policies:

~~~java
// Intentional pseudocode; not a standalone Java program.
// Dependencies/services and transaction APIs are hypothetical.
Decision decision = classifyPurely(event);
if (decision.accepted()) {
    service.processAtomically(event); // Perform controlled side effects.
}
~~~

In distributed systems, "atomically" does not happen automatically just by calling a single method. You may need a saga, outbox/inbox pattern, idempotency keys, or an appropriate transaction mechanism. The method name here merely clarifies **where responsibility lives**, without promising that a single call guarantees exactly-once execution.

One more point: diagnostic logging inside a guard **is also a side effect**, albeit lighter than charging a payment. Logging for debugging purposes is sometimes acceptable, but if an audit log has legal or business significance, it is part of the workflow and should not be hidden inside a predicate.

## 12. Common pitfalls and fixes table

| Common Pitfall | Consequence | How to Improve |
| --- | --- | --- |
| `when gateway.charge(...)` | May charge before branch is selected; hard to roll back | Guard only decides; service performs charge explicitly |
| `when repository.save(...)` | Write operation occurs inside condition | Move persistence into case body or service |
| Helper named `isEligible` that sends email | Misleading name implies purity | Separate `isEligible` and `notify` |
| Guard calls an API with timeout | Errors/exceptions affect branching, unpredictable latency | Fetch data or handle errors in service before classifying |
| Guard returns false after incrementing counter/reserving stock | Side effect persists even though case was not selected | Use pure predicates; perform actions after decision |
| `case T var -> ...` before `case T var when ...` | Guarded case is dominated | Place guarded cases before unguarded cases |
| Only guarded cases, no fallback for subtype | May fail exhaustiveness or miss values failing the condition | Add unguarded case for same type or appropriate handler |
| Calling `name.isBlank()` when component can be `null` | Throws `NullPointerException` in guard | Check `name != null && ...` |
| Compressing multiple rejection reasons into one Boolean | Loses error details, hard to test | Return `ValidationResult`/`Decision` with reason codes |
| Guard reads volatile state and body writes later | TOCTOU, decision based on stale data | Use transactions, versioning, or controlled rechecks |
| Assuming a false guard rolls back | `switch` does not manage side effects | Design explicit rollback/compensation |
| Treating compiler acceptance as sound architecture | Java does not forbid side-effecting helpers in `when` | Code reviews, tests, and separation of responsibilities |

You do not need to turn every guard into a helper. Prioritize changing **guards that involve state, I/O, hard-to-read conditions, or need to return detailed errors**.

## 13. Self-practice exercises

### Exercise 1. Identifying guards with side effects

What is wrong with the following snippet?

~~~java
// Illustrative pseudocode.
case Payment(var id, var amount)
        when sendEmail(id) && charge(amount) -> "Success";
~~~

**Answer:** `sendEmail` and `charge` can cause side effects right inside the branch-selection condition. If `sendEmail` returns `true` but `charge` returns `false` or throws an exception, the email may already have been sent. You should classify using pure data, and perform email sending/charging in a service with proper transaction and error handling.

### Exercise 2. Writing an appropriate guard

Given the record:

~~~java
record Registration(String username, int age) {}
~~~

For `Object input`, return `"Eligible"` if `username` is non-`null`, non-blank, and `age >= 18`; return `"Invalid registration"` for any other `Registration`; `"Missing"` if the selector is `null`; and `"Other"` for any other type.

**Answer:**

~~~java
// Java 21+ snippet.
String label = switch (input) {
    case Registration(var username, var age)
            when username != null && !username.isBlank() && age >= 18 ->
            "Eligible";
    case Registration(var username, var age) -> "Invalid registration";
    case null -> "Missing";
    default -> "Other";
};
~~~

The guard only reads record data without writing anything, fitting a simple classification purpose.

### Exercise 3. Side effects when a guard is `false`

In `SideEffectGuardDemo`, why does `calls` still increment after `route(-2)` returns `"not positive"`?

**Answer:** The pattern `Integer number` matched, so `badCheck(-2)` was called. The statement `calls++` ran before the method returned `false`. A false guard only prevents the first case from being selected; it **does not reverse** statements already executed inside the guard.

### Exercise 4. Needing detailed error codes

A validation needs to return `INVALID_ID`, `INVALID_QUANTITY`, `OUT_OF_STOCK`. Should you write `when isValidId(id) && isValidQuantity(qty) && reserveStock(qty)`?

**Answer:** No. `reserveStock` is an operation with side effects. If you need specific error codes, extract pure validation into a `ValidationResult` function or explicit steps. Reserving stock requires a dedicated service that handles inventory counts, transactions/concurrency, and write-time failures.

### Exercise 5. When to use a named predicate?

Suppose a guard contains:

~~~java
when id != null && !id.isBlank()
    && units > 0 && priceCents > 0
~~~

When should you extract it into `when validOrder(id, units, priceCents)`?

**Answer:** When the name `validOrder` clarifies the rule or the logic is reused/tested independently, and the helper **causes no side effects**. Extraction is unnecessary if the expression is short, clear, and appears in only one place. If validation needs to return failure reasons, use a detailed result type instead of a Boolean.

## 14. Checklist for reviewing guards in a codebase

When reviewing a `case ... when ...`, ask these questions:

1. Does the guard only **read** and check data, or does it perform update/insert/send/charge/reserve?
2. If the guard returns `false`, **have any side effects already occurred**?
3. If a helper in the guard throws an exception, does the caller know the failure path and handle it properly?
4. Is the predicate `null`-safe and does it use short-circuiting correctly?
5. Is the guard cheap and easy to understand, or is it hiding a chain of external checks/dependencies?
6. Is the guarded case placed before the general case of the same type? Is there a proper fallback for values that fail the guard?
7. If multiple guards can be true simultaneously, is branch priority intentionally designed and tested?
8. If a policy depends on mutable data, could the check result become stale before a write occurs?
9. If multiple error messages are needed, is a Boolean guard expressive enough, or should a validation result be used?
10. Can **pure `decide`** be clearly separated from **side-effecting `execute`** for easier testing and maintenance?

## 15. Summary

- `when` is an **additional condition to select a branch after a pattern matches**, not a place to execute business workflows.
- Guards may contain **simple, pure business conditions**. There is no need to eliminate all business predicates just because they have domain meaning.
- Side effects in a guard can occur **even if the condition returns `false`**; exceptions from a guard **do not automatically fall through to a fallback**.
- Keep pure checks and classification in the appropriate part of `switch`; place data writes, payments, notifications, critical audits, and transactions in **branch bodies or services with clear responsibilities**.
- When validation is complex or requires detailed failure reasons, use a pure helper returning `Decision`/`ValidationResult` instead of an unreadable guard chain.
- The compiler assists with type checking, scope, dominance, and exhaustiveness; **the compiler does not prove a guard has no side effects** or that a workflow is transactionally safe.
- Test pattern matches, true/false guards, `null`, exceptions, concurrency, and retries according to your system's contract.

**Official references:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html).
