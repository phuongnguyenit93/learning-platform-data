# Keeping Case Branches at the Same Level of Abstraction in Java Pattern Matching

## 1. What Is the “Same Level of Abstraction”?

In a `switch`, every `case` branch should answer **the same question at the same level of meaning**. If the `switch` acts as an event handler selector, the branches should all select a handler; if it classifies shapes, the branches should all return a classification result; if it converts a data type into a DTO, the branches should all return the corresponding DTO.

Example of expressing intent clearly:

```java
// Illustration; types and handlers are defined in the appropriate layer.
return switch (event) {
    case OrderCreated created -> handleCreated(created);
    case PaymentReceived payment -> handlePayment(payment);
    case OrderCancelled cancelled -> handleCancelled(cancelled);
};
```

All three branches share one meaningful pattern: **which event → the processing rule for that event**. The `switch` does not need to expose quantity validation, payment amount checks, or cancellation reason formatting.

A hard-to-read `switch` often forces the reader to constantly jump between levels:

- One branch just returns the event type name.
- One branch directly accesses the database and writes logs.
- One branch calls an application-level service.
- One branch processes a string and throws an exception.
- One branch has dozens of business conditions inside `when`.

The branches above may be syntactically valid, but **the responsibility of the `switch` as a whole is no longer clear**. Readers find it hard to predict where to make changes when adding a new input type or modifying a processing policy.

**Important:** keeping the same level of abstraction does not require branches to have the same number of lines, use the same helpers, or have the same complexity. A very small calculation can be kept inline if it clearly expresses the same purpose. The goal is to reduce reading comprehension cost and the risk of modifying code, not to make branches look identical in form.

This lesson belongs to Java Core Pattern Matching. Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) have both been standard since **Java 21**. The complete program below uses **JDK 21+**, without needing `--enable-preview`. The design principles remain useful for enum or traditional `switch` statements as well.

## 2. Defining a Single Responsibility for a Switch

Before coding, write one sentence: **“This switch is used to ...”**.

| Role | Expressing each case at the same level | Signs of mixed levels |
| --- | --- | --- |
| Classification | Every `case` determines a label/domain state | One case saves to the database, another only returns a label |
| Dispatching | Every `case` selects an appropriate handler | One case dispatches, another performs all detailed steps itself |
| Transformation | All cases return a DTO/result with the same contract | One case returns a DTO, another returns an infrastructure object |
| Decision | All cases produce a `Decision`/`Result` for a business rule | One case makes a decision, another prints to console and returns nothing |
| Interpretation | Each case turns a value into the same form of description | One case parses/calls an external API, another formats a String |

Just because branches all return `String` does not mean they are at the same level of abstraction. For example, if one case builds a label string from fields while another makes an HTTP call to update an order and then returns a string, **their side-effect contracts differ** even though the return type is the same.

Use these questions:

1. Can a reader predict the role of every case after reading the name of the `switch` method?
2. Does each case have the same kind of output/action at that boundary?
3. When adding a new subtype, is there one clear place to put its corresponding handling?
4. Does any case force the reader to understand low-level details such as SQL, networking, or byte formatting while other cases only express business logic?

If the answer is no, revisit the responsibility boundary.

## 3. Detecting a Switch That Mixes Dispatch with Processing Details

The example below **is only a sketch**, not a standalone runnable program; the services/repositories are assumed to already exist:

```java
switch (event) {
    case OrderCreated created -> {
        if (created.orderId() == null ||
                created.orderId().isBlank()) {
            throw new IllegalArgumentException("Invalid order id");
        }
        repository.insert(created.orderId(), created.itemCount());
        audit.write("created: " + created.orderId());
    }

    case PaymentReceived payment ->
        paymentService.handle(payment);

    case OrderCancelled cancelled ->
        System.out.println("Cancel " + cancelled.orderId());
}
```

The issue is not having many lines, but **mixing three roles**: data validation + persistence, service dispatch, and console output. When changing processing rules, you have to inspect part of the `switch` and an external service, and then check inconsistent side effects.

Rewriting the dispatching part in the same style:

```java
// Sketch: handlers are available in the application layer.
switch (event) {
    case OrderCreated created ->
        createdHandler.handle(created);
    case PaymentReceived payment ->
        paymentHandler.handle(payment);
    case OrderCancelled cancelled ->
        cancelledHandler.handle(cancelled);
}
```

makes the “select the right handler” structure clear. Validation rules, transactions, auditing, retries, and persistence must be placed in the layer with the corresponding authority and responsibility. **Do not treat moving side effects as a guaranteed equivalent refactor**: execution order, transaction scope, exceptions, and retry policies may change.

## 4. How Pattern Matching Supports This Organization

### Type patterns

```java
case OrderCreated created -> handleCreated(created);
```

This branch checks the type and binds the variable `created` of type `OrderCreated`. There is no need to manually write `instanceof` + cast. If every case follows the pattern “which type → handle that type”, the structure is very easy to scan.

### Record patterns

```java
record Point(int x, int y) {}

// Illustration inside an appropriate switch:
case Point(var x, var y) -> describePoint(x, y);
```

A record pattern both checks `Point` and deconstructs its components in declaration order. If the purpose of the `switch` is to convert structures into the same form of description, deconstructing the two components directly can make the intent clear.

However, deeply nested patterns do not automatically make intent clearer:

```java
record Customer(String name, boolean vip) {}
record Purchase(Customer customer, long amount) {}

// Illustration inside an appropriate switch:
case Purchase(Customer(var name, var vip), var amount)
        when vip && amount >= 1000L ->
    makePriorityDecision(name, amount);
```

If there is only one `vip` condition and one amount threshold, the code may still be readable. But if `when` adds checks for credit limits, region codes, effective dates, customer names, feature flag configurations, and database state, the `switch` knows too many details. You can move to `case Purchase p when isPriorityPurchase(p) -> ...`, or `case Purchase p -> classifyPurchase(p)` if you want the switch to dispatch strictly by type.

### `when` and conditions

`when` lets you distinguish cases of **the same type** with different rules. Using a guard is appropriate when the guard is **short and at the same level of meaning as selecting the case**. Complex guards should be named or moved into the handler.

Read the order carefully:
- The pattern must match first; only then is the guard evaluated.
- If the guard is false, the `switch` evaluates the next branch.
- Pattern variables are scoped to `when` and the branch body; they do not automatically exist in other cases.
- A guarded/more specific case must usually come **before** a broader case.

## 5. Complete Java 21 Program: Every Case Returns a Decision

Model three order events: order creation, payment receipt, and order cancellation. The program illustrates **classifying requests into decisions**, without performing real payments, database writes, or system updates.

Create the file **`SameLevelSwitchDemo.java`**:

```java
public class SameLevelSwitchDemo {

    sealed interface OrderEvent
            permits OrderCreated, PaymentReceived, OrderCancelled {}

    record OrderCreated(String orderId, int itemCount)
            implements OrderEvent {}

    record PaymentReceived(String orderId, long amount)
            implements OrderEvent {}

    record OrderCancelled(String orderId, String reason)
            implements OrderEvent {}

    record Decision(String status, String detail) {}

    static boolean hasId(String id) {
        return id != null && !id.isBlank();
    }

    // The switch does only one thing: dispatch to the appropriate decision handler.
    static Decision route(OrderEvent event) {
        return switch (event) {
            case null ->
                new Decision("REJECTED", "Không có sự kiện");
            case OrderCreated created ->
                handleCreated(created);
            case PaymentReceived payment ->
                handlePayment(payment);
            case OrderCancelled cancelled ->
                handleCancelled(cancelled);
        };
    }

    static Decision handleCreated(OrderCreated event) {
        if (!hasId(event.orderId())) {
            return new Decision("REJECTED", "Thiếu mã đơn hàng");
        }
        if (event.itemCount() <= 0) {
            return new Decision(
                "REJECTED", "Số mặt hàng không hợp lệ");
        }
        return new Decision(
            "CREATED",
            event.orderId() + ": " + event.itemCount() + " mặt hàng");
    }

    static Decision handlePayment(PaymentReceived event) {
        if (!hasId(event.orderId())) {
            return new Decision("REJECTED", "Thiếu mã đơn hàng");
        }
        if (event.amount() <= 0) {
            return new Decision(
                "REJECTED", "Số tiền không hợp lệ: " + event.orderId());
        }
        return new Decision(
            "PAID", event.orderId() + ": " + event.amount());
    }

    static Decision handleCancelled(OrderCancelled event) {
        if (!hasId(event.orderId())) {
            return new Decision("REJECTED", "Thiếu mã đơn hàng");
        }
        if (event.reason() == null || event.reason().isBlank()) {
            return new Decision(
                "REJECTED", "Thiếu lý do hủy: " + event.orderId());
        }
        return new Decision(
            "CANCELLED", event.orderId() + ": " + event.reason());
    }

    static void show(OrderEvent event) {
        Decision decision = route(event);
        System.out.println(
            decision.status() + " | " + decision.detail());
    }

    public static void main(String[] args) {
        show(new OrderCreated("O-1", 2));
        show(new PaymentReceived("O-1", 1200));
        show(new OrderCancelled("O-2", "Trùng đơn"));
        show(new PaymentReceived("O-3", 0));
        show(new OrderCreated("  ", 1));
        show(new OrderCancelled("O-4", ""));
        show(null);
    }
}
```

Compile with JDK 21 or newer:

```bash
javac --release 21 -encoding UTF-8 SameLevelSwitchDemo.java
java SameLevelSwitchDemo
```

Expected output:

```text
CREATED | O-1: 2 mặt hàng
PAID | O-1: 1200
CANCELLED | O-2: Trùng đơn
REJECTED | Số tiền không hợp lệ: O-3
REJECTED | Thiếu mã đơn hàng
REJECTED | Thiếu lý do hủy: O-4
REJECTED | Không có sự kiện
```

### Why is the switch in this program at the same level?

**`route` only dispatches.** The `OrderCreated`, `PaymentReceived`, and `OrderCancelled` cases all forward the input to a helper returning `Decision`. The reader understands the structure before having to inspect the details of each rule.

**The helpers are at the policy level.** `handleCreated` can check quantity, `handlePayment` checks amount, and `handleCancelled` checks reason. The methods do not need equal line counts; what matters is that each method handles the policy of one event.

**`hasId` shares a low-level rule.** Checking whether an ID is null/blank is named and written once. If the domain later changes the ID format, the place to update is clearer than repeating a long guard across multiple cases.

**`Decision` unifies the output.** The caller `show` does not need to know that each handler returns a different type; it only handles `status` and `detail`. In a real system, a status enum or a sealed result hierarchy with a stronger contract can be used.

**`case null` handles boundary errors with the same output type.** Although it does not call a handler, the null case still does the exact job of the switch: deciding the result for an input. “Same level” does not require every case to call a method.

**`sealed interface` supports an exhaustive switch.** Because `OrderEvent` only permits three subtypes in this model, a `switch expression` with the corresponding type patterns can be exhaustive without `default`. When a new permitted subtype is added, the compiler forces re-evaluating the dispatch site if no branch covers it yet.

### Scenarios to test

| Input | Reason | Output |
| --- | --- | --- |
| `new OrderCreated("O-1", 2)` | Valid ID, positive item count | `CREATED | O-1: 2 mặt hàng` |
| `new PaymentReceived("O-1", 1200)` | Valid ID, positive amount | `PAID | O-1: 1200` |
| `new OrderCancelled("O-2", "Trùng đơn")` | Has ID and reason | `CANCELLED | O-2: Trùng đơn` |
| `new PaymentReceived("O-3", 0)` | Non-positive amount | `REJECTED | Số tiền không hợp lệ: O-3` |
| `new OrderCreated("  ", 1)` | ID consists only of whitespace | `REJECTED | Thiếu mã đơn hàng` |
| `new OrderCancelled("O-4", "")` | Empty reason | `REJECTED | Thiếu lý do hủy: O-4` |
| `null` | Null selector policy | `REJECTED | Không có sự kiện` |

The table helps verify classification and output consistency. These are demo rules; they do not replace real transactional requirements such as idempotency, authorization, order state, retries, and atomic transactions.

## 6. Same Output Type Is Not Enough: Side Effects Must Also Be Consistent

A `switch expression` can have cases that all return `String` yet differ vastly in responsibility:

```java
// SKETCH: infrastructure objects are not declared here.
return switch (event) {
    case OrderCreated c -> "New: " + c.orderId();
    case PaymentReceived p ->
        paymentService.record(p).toString();
    case OrderCancelled c ->
        repository.delete(c.orderId()) ? "OK" : "FAILED";
};
```

The first branch only formats; the second calls a service; the last mutates persistence. All return `String`, but **the same static type does not mean the same abstraction**.

A clearer organization:

```text
OrderEvent
    |
    v
switch by subtype            = SELECT handler
    |
    +--> handleCreated       = DECISION for Create
    +--> handlePayment       = DECISION for Payment
    +--> handleCancelled     = DECISION for Cancel
    |
    v
Decision / Result            = shared CONTRACT
    |
    v
delivery boundary            = external ACTION (if any)
```

Not every application needs a multi-layered architecture like the diagram. This is a way to separate responsibilities when thinking about design: the `switch` itself should reveal a choice at the level for which its method is named.

### Side effects and refactoring

If old code wrote an audit log before writing to the repository, moving to a new helper could accidentally reverse the order. If one branch catches exceptions while another lets them propagate, grouping them into handlers can also change the error contract. Therefore, check:

- execution order of I/O, auditing, and metrics;
- transaction scope;
- failure cases at each step;
- idempotency and retries;
- when the output is produced for the caller.

Refactoring for readability **does not exempt you from preserving behavior**.

## 7. `when` Guards and Level of Abstraction

A guard should be an easy-to-understand condition directly about **branch selection**:

```java
// Illustrative case labels in a switch with appropriate handlers.
case PaymentReceived p when p.amount() <= 0 ->
    rejectPayment(p);
case PaymentReceived p ->
    acceptPayment(p);
```

Both cases are at the same level of “making a decision for a payment”. The short guard only distinguishes a special case.

If a rule consists of ten conditions, instead of:

```java
// SKETCH: long guard mixing multiple policies.
case PaymentReceived p
        when p.amount() > 0
            && p.orderId() != null
            && !p.orderId().isBlank()
            && isCustomerActive(p)
            && isWithinCreditLimit(p)
            && passesRegionalPolicy(p) ->
    acceptPayment(p);
```

you can name it:

```java
case PaymentReceived p when isEligiblePayment(p) ->
    acceptPayment(p);
case PaymentReceived p ->
    rejectPayment(p);
```

However, the `isEligiblePayment` helper should be a condition with a clear contract, tests, and no unexpected side effects. Do not pick a generic name like `check(p)` that forces reviewers to open the method just to understand its intent.

### Dominance: specific branches must come first

**Intentionally wrong example, will not compile**:

```java
case PaymentReceived p -> acceptPayment(p);
case PaymentReceived p when p.amount() <= 0 ->
    rejectPayment(p); // Dominated by the broader case above.
```

`case PaymentReceived p` above accepts every non-null `PaymentReceived`. The guarded branch below becomes unreachable; the compiler reports dominance. Write the guarded branch first, then the general branch.

A switch with clear intent but wrong case ordering is still invalid code. During review, check both **level of abstraction** and Java's pattern matching rules.

### Pattern mismatch and a false guard are two different things

- Input `OrderCreated` does not match the pattern `PaymentReceived p`.
- Input `PaymentReceived("O-1", 100)` matches the type pattern, but the guard `amount <= 0` returns false.
- A false guard causes the `switch` to evaluate the next branch; pattern variables of the current case are not automatically in scope in other cases.
- With nested record patterns, a null sub-record component can cause the entire pattern not to match before the guard is evaluated.

These differences must be reflected through explicit fallback cases or corresponding tests.

## 8. When to Inline, When to Extract a Helper?

**Keep inline when:**

- The expression is short and expresses the exact level of intent of the whole switch.
- A case only returns a label, converts a single value, or calls a simple operation.
- Extracting a helper loses directness without increasing reusability or testability.

Example:

```java
// Illustration inside a method with enum State:
return switch (state) {
    case NEW -> "Mới";
    case PAID -> "Đã thanh toán";
    case CANCELLED -> "Đã hủy";
};
```

This is a same-level mapping. Forcing each branch to call `newLabel()`, `paidLabel()`, `cancelledLabel()` just to achieve “one method call per line” can make the code harder to read.

**Extract a helper when:**

- A branch consists of multiple independent business rules.
- Deeply nested patterns create many variables used only in certain conditions.
- The same validation is repeated across multiple cases.
- A branch has side effects that require transaction/error management.
- You need to unit test a policy without running the entire dispatcher.
- The helper name describes a domain meaning much more clearly than a long chain of conditions.

**Do not extract solely based on line count.** A case with a longer `-> { ... }` block can still be reasonable if the entire block produces one small, directly related result. A newly extracted helper that requires ten parameters can be a sign of a poor abstraction.

## 9. Null, Sealed, and Exhaustiveness in the Same Switch

In the Java 21 code in section 5:

```java
return switch (event) {
    case null -> new Decision("REJECTED", "Không có sự kiện");
    case OrderCreated created -> handleCreated(created);
    case PaymentReceived payment -> handlePayment(payment);
    case OrderCancelled cancelled -> handleCancelled(cancelled);
};
```

`case null` decides how to handle a null selector. In an enhanced `switch` using pattern matching, you should not rely on `default` as an alternative way to catch null. Placing a policy-explicit null case stays at the same level of **deciding the result**, without forcing a helper call.

Because the selector type is a `sealed interface` with three subtypes, the switch expression can be exhaustive without `default`. This is useful: adding a new permitted subtype normally forces updating the dispatch site when existing cases do not yet cover that subtype.

Conversely, when the selector has type `Object`, you must consider objects outside the event set. A switch expression that only handles a few specific subtypes will not be exhaustive without a sufficiently broad branch. Choosing to add `default`, a general type pattern, or changing the API must follow the method's contract, not a desire for less code.

**Note:** a very broad `default` can hide the need to add handling for a new domain variant. Do not unconditionally add `default` to every sealed switch just to avoid compiler reminders when the hierarchy is extended.

## 10. Behavior-Preserving Refactoring Process

**Step 1. Lock in the switch description sentence.** “Convert `OrderEvent` into `Decision`” is more specific than “handle event”.

**Step 2. List inputs and paths.** What subtypes, guards, null, invalid inputs, and default/fallbacks exist? For a switch expression, is it exhaustive?

**Step 3. Separate dispatch from details.** Mark code calling repositories, networking, auditing, data transformations, validation, or auxiliary calculations that do not share the same role as the other cases.

**Step 4. Name helpers after business concepts.** `handlePayment` or `toPaymentDecision` conveys scope better than `run1` or `doIt`.

**Step 5. Fix the output contract.** In the example, all handlers return `Decision`. In practice, this can be sealed result types expressing failure/success in a more type-safe way.

**Step 6. Preserve side effects.** Record the order and conditions of repositories, auditing, errors, retries, and transactions before moving code elsewhere.

**Step 7. Test before/after.** Compare outputs for each subtype, true/false guards, null, and invalid data. For I/O, also test exceptions, rollbacks, and call order.

**Step 8. Re-read the switch.** If a reviewer looks at the cases and immediately knows which policy the program is selecting, the refactor has achieved its goal. If they have to jump through multiple vaguely named helpers just to understand basic functionality, you may have over-extracted.

A change can shorten a switch and still fail to improve the design if it merely moves blocks of code into `helper1`/`helper2` without assigning proper responsibilities and contracts.

## 11. Code Review Checklist

| Question | What to check |
| --- | --- |
| Does the switch have a single named responsibility? | Method name and output share the same meaning |
| Does every case answer the same question? | No arbitrary mixing of dispatch/validation/IO |
| Do all cases share the same result contract? | Consistent output/side-effect types and semantics |
| Are guards short and at the right level of meaning? | Avoid long unnamed business conditions |
| Do specific cases come before general cases? | Avoid dominance |
| Are pattern variables properly scoped? | Used in matching guard/branch, not leaked to other cases |
| Does the record pattern go deeper than necessary? | Avoid deconstructing unused components |
| Is a null sub-record distinguished from a null `var` component? | A sub-pattern may fail to match before evaluating the guard |
| Does a null selector have a clear policy? | `case null` or guarded before the switch |
| Is the sealed hierarchy handled exhaustively on purpose? | Adding new subtypes is not forgotten |
| Does the refactor test outputs and side effects? | Not just comparing the happy path |
| Do helper names express intent? | Do not create hollow abstraction layers |

## 12. Common Mistakes When Trying to Keep Cases at the Same Level

| Misconception | Risk | Suggestion |
| --- | --- | --- |
| “Every branch must be one line” | Creates meaningless helpers, increases navigation | Judge by intent, not line count |
| “Returning `String` in every branch is enough” | One branch has side effects, another only formats | Distinguish output type from responsibility |
| “Pattern matching guarantees clean code” | Overly deep nested trees, dense guards | Set boundaries and name policies appropriately |
| Putting `case Parent p` before `case Child c` | Child case is shadowed, may not compile | Put specific cases first |
| Putting an unguarded case before the same type with a guard | Guarded case is dominated | Reverse the order |
| Leaving heavy I/O inside dispatch branches | Hard to test and inconsistent | Move to the responsible layer |
| Moving side effects just to make code look neat | Changes order, transactions, exceptions | Write tests and verify |
| Using a broad `default` for every sealed hierarchy | Adding a subtype does not force updating the switch | Consider exhaustive type cases |
| Treating `default` as a guaranteed null branch | Runtime may handle null differently than expected | Set an explicit null policy |
| Extracting helpers with overly generic names like `handle`/`check` | Reviewers still have to dig deep | Name after the domain rule |
| Confusing a false guard with a pattern mismatch | Wrong fallback branch | Test each failure mode |
| Multiple cases returning errors without a shared contract | Hard for callers to use | Define a common result/decision |

## 13. Practice Exercises

**Exercise 1 — Write a description sentence.** For the sketch switch in section 3, identify the intended overall role. Mark each line belonging to dispatch, validation, persistence, and display. Refactor into three handlers without changing the processing contract.

**Exercise 2 — Sealed structure.** Declare `sealed interface Command permits Create, Update, Delete` and write a switch expression dispatching to three handlers that all return `Decision`. Include an explicit null policy.

**Exercise 3 — Dominance.** Write two `PaymentReceived` cases: an invalid-amount branch and a general branch. Try swapping their positions to observe the compiler error.

**Exercise 4 — Avoid over-engineering.** Given a mapping from an enum state to three display labels, explain why three separate helpers are not necessarily needed even though each branch is just a single expression.

**Exercise 5 — Add a subtype.** Run `SameLevelSwitchDemo.java`. Add `record OrderRefunded(String id, long amount) implements OrderEvent {}` and include it in `permits`. Observe how the compiler requires updating `route`; design `handleRefunded` returning the same `Decision`.

**Exercise 6 — Test guards.** Add `PaymentReceived("O-5", -10)` and `OrderCancelled("O-6", null)` to `main`. Predict the status and detail from the helpers; run to confirm.

**Exercise 7 — Policy and I/O.** A payment handler must send an audit after succeeding. Where would you place the audit so the dispatcher remains readable? List tests for the case where the audit throws an exception.

**Exercise 8 — Record pattern.** Given `Purchase(Customer(var name, var vip), var amount) when vip && amount >= 1000L`, compare keeping it inline versus moving the rule into `isPriorityPurchase`. State clearly when short deconstruction expresses intent better, and when a helper is easier to maintain.

## 14. Key Takeaways

**Keeping `case` branches at the same level of abstraction** means the cases expose the same **kind of decision or action**. In Java 21, type patterns, record patterns, `when`, and sealed hierarchies make dispatchers concise, type-safe, and easy to extend for new cases; however, they do not replace responsibility design.

Be sure to:
- Write one sentence describing the switch's responsibility.
- Place branches at the same domain/dispatch/transformation level.
- Move validation, I/O, or long rules into the appropriate helper/layer when doing so improves clarity.
- Keep outputs and null policies consistent while checking dominance and exhaustiveness.
- Do not force every case into one line or extract helpers just to make the code look uniform.
- When refactoring, compare results, exceptions, side-effect ordering, and transactions.

### References

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
