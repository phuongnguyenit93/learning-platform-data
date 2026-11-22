# Naming Pattern Variables to Preserve Domain Semantics in Java 21

## 1. Why Do Variable Names Matter When Using Pattern Matching?

Pattern matching in Java allows checking the type or structure of data and **declaring variables right at the match site**. For example:

```java
if (event instanceof PaymentReceived payment) {
    process(payment);
}
```

The `PaymentReceived payment` part is a **type pattern**; `payment` is a **pattern variable**. The name `payment` helps readers recognize what role the value plays in the business flow. If it were simply named `p` or `x`, the compiler would still accept it, but readers would have to infer its meaning themselves.

**Domain** is the business area that the program models, such as orders, payments, shipping, bookings, or invoices. **Preserving domain semantics** means that variable names accurately express the role of the data where it is used: who the buyer is, which amount was collected, which ID belongs to which transaction, and which location is the origin or destination.

Compare two ways of writing the same condition:

```java
// Unclear role:
if (value instanceof PaymentReceived p) {
    audit(p);
}

// Clearer role:
if (value instanceof PaymentReceived receivedPayment) {
    audit(receivedPayment);
}
```

The two snippets above are **illustrative code snippets**; the domain types and methods must be defined in the application. In Java 21, the pattern matching mechanism of both snippets is identical. The value of a good name lies in its ability to explain **why** a value is used in the business flow and to reduce misunderstandings when modifying code.

This is especially important for **record patterns**, because a single line can declare multiple pattern variables at once:

```java
record Transfer(String fromAccountId, String toAccountId, long amountVnd) {}

// Pattern reading transfer data:
if (value instanceof Transfer(
        String sourceAccountId,
        String destinationAccountId,
        long transferAmountVnd)) {
    // Readers can immediately see each value's role without checking the record declaration
}
```

`sourceAccountId` and `destinationAccountId` both have type `String`; Java types cannot distinguish their **business roles**. Variable names must do that job.

## 2. Distinguishing Four Kinds of Names When Reading a Pattern

Consider:

```java
record Order(String orderId, String buyerId) {}

if (input instanceof Order(String matchedOrderId, String purchasingCustomerId)) {
    // ...
}
```

There are four different components:

| Component | Example | Meaning |
| --- | --- | --- |
| **Domain type** name | `Order` | Defines the business concept |
| **Record component** name | `orderId`, `buyerId` | Component data as defined by the record |
| **Pattern variable** name | `matchedOrderId`, `purchasingCustomerId` | Local variable declared when the pattern matches |
| **Value under test** name | `input` | Original variable holding the object to be classified |

In a record pattern, Java matches components **by position and type**, not by similarity between the pattern variable name and the record component name. `purchasingCustomerId` still receives the **second component** (`buyerId`) because it stands in the second position.

It is not mandatory to give a pattern variable the same name as the component. However, when renaming, preserve the correct meaning: if `buyerId` is the buyer's ID, then `supplierId` is a **misleading** name, even though the code compiles.

**Core rule:** a pattern variable name must express *what this value is in the processing context*, while the record component's type and position determine *which value is bound*.

## 3. Name by Business Role, Not Just by Type

A `String` can be an order ID, a customer ID, an email address, or an error message. A `long` can be a monetary amount, a timestamp, or a quantity. Names that only reflect the type are insufficient to convey meaning:

| Unclear Name | Domain-Expressive Name | Reason |
| --- | --- | --- |
| `s`, `str` | `orderId`, `customerEmail` | States the exact kind of string |
| `n`, `num` | `quantity`, `paymentAmountVnd` | States the exact quantity, optionally with unit |
| `p`, `obj` | `receivedPayment`, `targetProduct` | Associates the object with its role |
| `item1`, `item2` | `sourceItem`, `replacementItem` | Distinguishes two objects of the same type |
| `a`, `b` | `originCity`, `destinationCity` | Prevents reversing direction in route handling |
| `r`, `res` | `approvalResult`, `declineReason` | Helps clarify which branch is being evaluated |
| `data`, `value` | `matchedOrder`, `selectedShipment` | Reduces ambiguity when multiple data sources coexist |

Longer names are not always better. `orderId` is usually better than `theUniqueIdentifierOfTheOrderBeingProcessed`. Choose **the shortest name that still clearly distinguishes the role within the scope being read**.

For example, when both ends of a route are `Location`:

```java
record Location(String city) {}
record ShipmentRoute(Location origin, Location destination) {}

if (candidate instanceof ShipmentRoute(
        Location(String originCity),
        Location(String destinationCity))) {
    System.out.println(originCity + " -> " + destinationCity);
}
```

`originCity` and `destinationCity` clarify the shipping direction. Names like `city1` and `city2` obscure important information; a maintainer could easily swap the two values without the compiler noticing.

## 4. Naming Type Patterns to Match the Matched Object

A type pattern has the basic syntax `Type variableName`, for example:

```java
if (message instanceof PaymentCommand paymentCommand) {
    dispatch(paymentCommand);
}
```

`paymentCommand` is the value that matched the `PaymentCommand` type. When naming it, choose among:

- **Domain nouns:** `order`, `invoice`, `customer`, `payment`.
- **Nouns with an operational role:** `originalOrder`, `replacementOrder`, `selectedInvoice`, `sourceAccount`.
- **State-qualified names when the state is guaranteed by the type or logic:** `approvedOrder` for a type that genuinely models `ApprovedOrder`, or a variable used inside a branch that has already verified that state.

Example with hypothetical domain classes:

```java
// SNIPPET: OrderEvent and OrderCancelled types are defined in the application.
if (event instanceof OrderCancelled cancelledOrderEvent) {
    notifyCustomer(cancelledOrderEvent);
}
```

`cancelledOrderEvent` is more accurate than `cancelledOrder` if the matched data is actually an **event**, not the order itself.

### Avoid Names That Promise Something Unproven

A type match does not automatically validate all business rules:

```java
// Misleading name when only checking String:
if (input instanceof String verifiedEmail) {
    sendNotice(verifiedEmail);
}
```

`String` does not guarantee that the string is a valid or verified email. The name `verifiedEmail` creates a false impression.

A clearer approach:

```java
if (input instanceof String emailCandidate
        && isValidEmail(emailCandidate)) {
    sendNotice(emailCandidate);
}
```

Here `isValidEmail` is an **illustrative** business validation function that requires a real implementation. The variable `emailCandidate` still accurately describes the input data; validity is expressed by the condition. If the system has a `VerifiedEmail` type that genuinely enforces this invariant, using the type pattern `VerifiedEmail verifiedEmail` has a much stronger basis.

## 5. Record Patterns: Name According to Component Position and Meaning

In Java 21, record patterns allow extracting multiple values directly from components:

```java
record Invoice(String invoiceId, String customerId, long totalVnd) {}

if (candidate instanceof Invoice(
        String matchedInvoiceId,
        String billedCustomerId,
        long invoiceTotalVnd)) {
    // ...
}
```

The components of `Invoice` have a fixed order: `invoiceId`, `customerId`, `totalVnd`. The pattern receives data in that order regardless of how the variables are named. Therefore, when refactoring a record pattern, **check the position first, then choose the name**.

An example of a wrong name that is still syntactically valid:

```java
// SEMANTIC BUG: the two names mislead readers into thinking the roles are swapped
if (candidate instanceof Invoice(
        String customerId,
        String invoiceId,
        long totalVnd)) {
    // customerId actually receives the invoiceId component;
    // invoiceId actually receives the customerId component!
}
```

This is a dangerous bug because both components are `String`. The compiler cannot detect whether you misnamed the roles. The fix is to rename according to the **actual position**:

```java
if (candidate instanceof Invoice(
        String invoiceId,
        String customerId,
        long invoiceTotalVnd)) {
    // ...
}
```

### When to Use `var` in a Record Pattern?

```java
if (candidate instanceof Invoice(
        var invoiceId,
        var customerId,
        var invoiceTotalVnd)) {
    // ...
}
```

`var` lets Java infer the types of the components: the first two variables are `String`, and the last is `long`. It does **not** infer domain meaning. Therefore, when using `var`, variable names need even more clearly to express roles and units.

You can keep explicit types when they help the reader:

```java
if (candidate instanceof Invoice(
        String invoiceId,
        String customerId,
        long invoiceTotalVnd)) {
    // ...
}
```

Both forms are valid record patterns in Java 21. Choose the style consistent with your coding conventions and the clarity of the code.

## 6. Nested Record Patterns: Variable Names Must Reflect the Data Path

Nested records force readers to track multiple layers:

```java
record Customer(String id, String displayName) {}
record Address(String city, String district) {}
record Delivery(Customer recipient, Address destination) {}

if (candidate instanceof Delivery(
        Customer(String recipientId, String recipientName),
        Address(String destinationCity, String destinationDistrict))) {
    // ...
}
```

Reading along the data path:

```text
Delivery
├── recipient: Customer
│   ├── id          -> recipientId
│   └── displayName -> recipientName
└── destination: Address
    ├── city        -> destinationCity
    └── district    -> destinationDistrict
```

Here `recipientName` is better than `name`, because business code might also involve a sender's name, recipient's name, or agent's name. Similarly, `destinationCity` is better than `city` if an origin also exists.

**Do not copy the entire path into the name.** `deliveryDestinationAddressCityName` is usually too long. In a short block handling a single destination, `destinationCity` is clear enough.

### When Data Has Symmetric Roles

```java
record Account(String accountId) {}
record Transfer(Account source, Account destination, long amountVnd) {}

if (candidate instanceof Transfer(
        Account(String sourceAccountId),
        Account(String destinationAccountId),
        long transferAmountVnd)) {
    // sourceAccountId and destinationAccountId may have the same type,
    // but the transfer direction must be preserved.
}
```

*Source/destination*-based naming helps prevent business mistakes: transferring in the wrong direction or logging the wrong account. When destructuring data of the same type by position, this is essential information.

## 7. Pattern Variables in `switch`: Binding Names to Each Domain Branch

Pattern matching for `switch` is a standard feature in Java 21. Each branch can bind a pattern to a domain state or variant:

```java
sealed interface PaymentOutcome permits Paid, Rejected {}
record Paid(String paymentId, long amountVnd) implements PaymentOutcome {}
record Rejected(String reason) implements PaymentOutcome {}

static String describe(PaymentOutcome outcome) {
    return switch (outcome) {
        case Paid(String paymentId, long paidAmountVnd)
                when paidAmountVnd >= 1_000_000L ->
            "Large payment " + paymentId;
        case Paid(String paymentId, long paidAmountVnd) ->
            "Payment " + paymentId + ": " + paidAmountVnd;
        case Rejected(String rejectionReason) ->
            "Rejected: " + rejectionReason;
    };
}
```

The variables carry clear meaning:

- `paymentId`: the ID of the successful payment transaction, not to be confused with an order ID.
- `paidAmountVnd`: the amount **paid**, in **VND**.
- `rejectionReason`: the reason for **payment rejection**, not an arbitrary error.
- `when paidAmountVnd >= 1_000_000L`: the condition for the large-value branch. `when` is a **guard**, not a pattern variable.

The `Paid(...)` branches reusing the same variable names are valid because they are separate per-branch pattern declarations. The same name has the same meaning in both branches, so consistent usage is helpful. Conversely, you should not name an amount in a `Rejected` record `paidAmountVnd` if the record only stores the **intended payment** amount.

### Do Not Use Names Carrying Different Domain Meaning From the Matched Type

An example to avoid:

```java
// SNIPPET ILLUSTRATING POOR NAMING
case Rejected(String approvedReason) -> ...
```

The variable is actually a rejection reason, so naming it `approvedReason` distorts the business message. Java only checks syntax and types; it does not understand name semantics to report an error.

**State-based naming guideline:** `approvalReason`, `rejectionReason`, and `refundReason` should only be used when the corresponding data matches the modeled state.

## 8. Naming When Combining Patterns With `when`

A guard can clarify the branch selection condition:

```java
static String classify(Object candidate) {
    return switch (candidate) {
        case null -> "missing";
        case String couponCode when couponCode.isBlank() -> "blank coupon";
        case String couponCode -> "coupon: " + couponCode;
        default -> "unsupported";
    };
}
```

In this example:

- `couponCode` comes from the **processing context**, so it is more appropriate than `s`.
- Both `String couponCode` branches are **type patterns**, and each variable exists only within its own branch scope.
- `couponCode.isBlank()` is a guard. It **does not change the type** of the variable.
- The branch receiving a non-blank string still needs to distinguish "checked as non-blank" from "a valid coupon code in the system". These two are not synonymous.

Naming it `validatedCouponCode` directly on `String` just because of `when !couponCode.isBlank()` would overstate what is guaranteed: checking for non-blank does not verify whether the code exists, has expired, or applies to the current order.

## 9. Keep Domain Terminology, Units, and Timestamps Consistent

Three categories of information are easily lost when using generic names:

| Information Category | Easy to Confuse | Names to Consider |
| --- | --- | --- |
| **Role** | Two people/accounts/addresses of the same type | `payerId`, `payeeId`; `originCity`, `destinationCity` |
| **Unit** | `long amount` could be VND, USD cents, milliseconds | `amountVnd`, `amountCents`, `timeoutMillis` |
| **Timestamp** | Dates sharing type `LocalDate` | `orderedAt`, `paidAt`, `deliveredAt` (with an appropriate temporal type) |
| **State** | `total` differs from `paid`, `pending`, `refunded` | `invoiceTotalVnd`, `paidAmountVnd`, `refundAmountVnd` |
| **Identifier** | All are `String`, but identify different entities | `orderId`, `paymentId`, `customerId` |

Unit-qualified names do not replace strong domain typing (such as `Money`, `Currency`, `OrderId`), but they help reduce confusion when a domain temporarily uses primitive types.

Example:

```java
record Payment(String paymentId, long amountCents) {}

if (obj instanceof Payment(String paymentId, long chargedAmountCents)) {
    System.out.println(paymentId + ": " + chargedAmountCents + " cents");
}
```

If you want to display USD, you must convert cents to dollars according to business rules. Never simply rename `chargedAmountCents` to `chargedAmountUsd` while the value is still in cents.

### Consistent Vocabulary Within a Codebase

A team should standardize domain nouns: when to use `customer` vs. `buyer`, whether `accountId` is an account identifier or a user ID, and how `settledAmount` differs from `authorizedAmount`. When a record component uses `customerId` but a pattern variable uses `clientCode` without reason, readers have to guess whether they represent two different concepts.

Within a single method, names can be shorter when the context is clear. Only add prefixes such as `invoice`, `payment`, or `shipping` when they genuinely help distinguish between objects.

## 10. Scope and Name Conflicts When Renaming Pattern Variables

Good names must still obey **flow scoping**. A pattern variable can only be used where Java knows the pattern has matched.

```java
if (candidate instanceof Invoice invoice) {
    System.out.println(invoice); // Valid inside the matched branch
}
// System.out.println(invoice); // Error: out of flow scope
```

In the snippet above, `Invoice` is a **hypothetical** domain type. After the `if`, `candidate` might not be an `Invoice`, so `invoice` is not in scope.

One way to keep a meaningful name when needed in subsequent steps is a guard clause:

```java
static String requireCustomerId(Object value) {
    if (!(value instanceof String customerId)) {
        throw new IllegalArgumentException("customerId must be a String");
    }
    return customerId;
}
```

However, this method only checks the **type**; it does not verify that `customerId` has the right format or exists in the database. The name is clear, while domain validation must be performed in the appropriate place.

### Avoid Colliding With Variables Already in Scope

```java
// SNIPPET INTENTIONALLY DOES NOT COMPILE:
String orderId = "ORD-OLD";
if (candidate instanceof String orderId) {
    System.out.println(orderId); // Duplicate name declaration
}
```

Fix it by using names with clearly distinct roles:

```java
String existingOrderId = "ORD-OLD";
if (candidate instanceof String incomingOrderId) {
    System.out.println(incomingOrderId);
}
```

If both are order IDs from different sources, `existingOrderId` and `incomingOrderId` clarify the comparison's purpose. Avoid `orderId2` because it does not explain the difference.

With `switch`, each pattern branch has its own scope. Do not try to use `paidAmountVnd` from `case Paid(...)` in `case Rejected(...)`. If a value is needed after `switch`, return the result and assign it to a domain-named variable, such as `paymentSummary`.

## 11. Complete Program: Recognizing Domain Names Across Multiple Patterns

The file **`DomainPatternVariableNamesDemo.java`** below uses **standard Java 21** features and requires no preview flags.

```java
public class DomainPatternVariableNamesDemo {
    sealed interface PaymentOutcome permits Paid, Rejected {}

    record Paid(String paymentId, long amountVnd)
            implements PaymentOutcome {}

    record Rejected(String reason)
            implements PaymentOutcome {}

    record Customer(String customerId, String displayName) {}

    record Order(
            String orderId,
            Customer buyer,
            PaymentOutcome paymentOutcome) {}

    record City(String name) {}
    record Route(City origin, City destination) {}

    static String paymentSummary(PaymentOutcome outcome) {
        return switch (outcome) {
            case null -> "no payment outcome";
            case Paid(String paymentId, long paidAmountVnd)
                    when paidAmountVnd >= 1_000_000L ->
                "large payment " + paymentId + ": "
                        + paidAmountVnd + " VND";
            case Paid(String paymentId, long paidAmountVnd) ->
                "payment " + paymentId + ": "
                        + paidAmountVnd + " VND";
            case Rejected(String rejectionReason) ->
                "rejected: " + rejectionReason;
        };
    }

    static String orderSummary(Object candidate) {
        if (candidate instanceof Order(
                String orderId,
                Customer(String customerId, String customerName),
                Paid(String paymentId, long paidAmountVnd))) {
            return "order " + orderId + " for " + customerName
                    + " (" + customerId + "), payment " + paymentId
                    + ": " + paidAmountVnd + " VND";
        }
        return "order not paid";
    }

    static String routeSummary(Object candidate) {
        if (candidate instanceof Route(
                City(String originCity),
                City(String destinationCity))) {
            return originCity + " -> " + destinationCity;
        }
        return "unknown route";
    }

    public static void main(String[] args) {
        PaymentOutcome paid = new Paid("PAY-9", 1_500_000L);

        System.out.println(paymentSummary(paid));
        System.out.println(
                paymentSummary(new Paid("PAY-10", 250_000L)));
        System.out.println(
                paymentSummary(new Rejected("card declined")));
        System.out.println(paymentSummary(null));

        System.out.println(orderSummary(new Order(
                "ORD-1", new Customer("CUS-7", "Lan"), paid)));
        System.out.println(orderSummary(new Order(
                "ORD-2", new Customer("CUS-8", "Minh"),
                new Rejected("insufficient balance"))));

        System.out.println(routeSummary(new Route(
                new City("Hanoi"), new City("Danang"))));
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 DomainPatternVariableNamesDemo.java
java DomainPatternVariableNamesDemo
```

Stdout:

```text
large payment PAY-9: 1500000 VND
payment PAY-10: 250000 VND
rejected: card declined
no payment outcome
order ORD-1 for Lan (CUS-7), payment PAY-9: 1500000 VND
order not paid
Hanoi -> Danang
```

### Why Are These Names Helpful?

- `paidAmountVnd` is a value belonging to the successful payment state, **not** the order's total amount.
- `paymentId` differs from `orderId`; the two IDs should not be swapped when logging or returning results.
- `customerId` differs from `customerName`; even though both are `String`, each name aligns with the right component of `Customer`.
- `rejectionReason` belongs only to the `Rejected` variant, avoiding confusion with payment notes.
- `originCity` and `destinationCity` express the direction of `Route`, rather than `city1` and `city2`.
- `paymentSummary` is the result of `switch`, named after the domain; variables inside individual patterns are not leaked outside flow scope.

**Limitation to keep in mind:** `Paid` is a record representing a state in this example, not proof that a real-world payment system has actually settled the transaction. In a real application, names and models like `Paid`, `Settled`, and `Authorized` must accurately reflect business conventions.

## 12. Naming Practices That Cause Maintenance Bugs

### 12.1. Numbered Names When Values Have Distinct Roles

```java
// Hard to read:
case Route(City(var city1), City(var city2)) ->
    city1 + " -> " + city2;

// Clear roles:
case Route(City(var originCity), City(var destinationCity)) ->
    originCity + " -> " + destinationCity;
```

These two lines are **switch label snippets**, requiring the corresponding record types and a valid switch context. The second form clearly indicates the direction of travel.

### 12.2. Names Swapped Relative to Component Order

```java
record Refund(String originalPaymentId, String refundId, long amountVnd) {}

// The names below are SEMANTICALLY WRONG even though they compile:
if (obj instanceof Refund(
        String refundId,
        String originalPaymentId,
        long refundAmountVnd)) {
    // ...
}
```

Here `refundId` actually receives the **original payment ID**. The fix is to check the record declaration order again and write `String originalPaymentId, String refundId`. Be especially vigilant with records that contain multiple components of the same type.

### 12.3. Names Asserting an Unverified State

```java
if (obj instanceof String approvedOrderId) {
    // We only know obj is a String, not that the order has been approved
}
```

Replace it with `orderIdCandidate` or a name matching the input data; if you want `approvedOrderId`, place it in a branch with corresponding **business evidence** or use a type that represents the approved state.

### 12.4. Using Generic Names Across Consecutive Patterns

```java
// SNIPPET: hypothetical classes exist
switch (domainEvent) {
    case PaymentReceived event -> handlePayment(event);
    case OrderCancelled event -> handleCancellation(event);
    default -> handleUnknown(domainEvent);
}
```

The name `event` is not wrong: the type and branch are already clear. However, in long branches or when multiple objects appear together, `paymentReceivedEvent` and `orderCancelledEvent` can be clearer. Do not force every branch to use long names when the body is a single line; clarity must be judged in **context**.

### 12.5. Renaming in One Place While Forgetting Other Usages

When refactoring `case Paid(String id, long amount)` to `case Paid(String paymentId, long paidAmountVnd)`, update **every corresponding reference in the guard and branch body**. Use your IDE's *Rename Symbol* feature to avoid missing usages or accidentally renaming identical strings in other scopes.

## 13. A Workflow for Naming When Reading or Writing New Patterns

You can follow this sequence:

1. **Identify the domain object:** Is the value under test a payment event, an order, or an address? If the domain is unclear, read the type, fields, or record declaration.
2. **Identify each value's role:** Origin or destination, order ID or payment ID, total amount or collected amount?
3. **Read the exact component order:** Especially when multiple components are `String`, `long`, or the same record type.
4. **Choose the necessary noun and qualifiers:** `paymentId`, `sourceAccountId`, `refundAmountVnd`.
5. **Check the guarantee boundary:** Only use names meaning "validated/paid/approved" if the type or logic truly guarantees it.
6. **Keep scope tight:** Use the name within the matched branch; when a unified result is needed, assign it to a domain-meaningful result variable.
7. **Review distinguishability:** If swapping two variables of the same type would still compile without error, do the names help readers spot the mistake?
8. **Check consistency with the team glossary:** Prefer names already established in the domain model or public API.

Do not mechanically lengthen names just to pack in every detail. If there is only one `Order` in a short method, `order` can be a good name. If there is an *original order* and a *replacement order*, you must distinguish the two roles.

## 14. Exercises: Choosing Names That Reflect the Domain

**Exercise 1.** `record Shipment(Location pickup, Location dropoff) {}`. Which option makes more sense when nesting patterns?

```java
Shipment(Location(var first), Location(var second))
Shipment(Location(var pickupCity), Location(var dropoffCity))
```

**Answer:** The second line. `pickupCity` and `dropoffCity` express the meaning of the two components in order. Also check the declaration of `Location`: this example assumes `Location` has one component representing the city name.

**Exercise 2.** Given `record Charge(String paymentId, long amountCents) {}`, which naming is not misleading?

```java
Charge(var id, var amountUsd)
Charge(var paymentId, var chargedAmountCents)
```

**Answer:** The second line. The record stores **cents**, so `amountUsd` would suggest the wrong unit. `paymentId` indicates which entity owns the ID.

**Exercise 3.** Does `input instanceof String verifiedEmail` guarantee a verified email?

**Answer:** No. It only guarantees that `input` is a `String`. The name should reflect its actual state, such as `emailCandidate`, until verification logic is complete.

**Exercise 4.** In `record Transfer(String sourceId, String targetId) {}`, does the pattern `Transfer(String targetId, String sourceId)` automatically swap the component extraction order?

**Answer:** No. Java matches **by position**, so the variable named `targetId` at the start still receives the `sourceId` component. This is a naming error that can lead to a business bug undetected by the compiler.

**Exercise 5.** When is using `var` for a component pattern appropriate?

**Answer:** When the type is easy to infer from the record and the variable name already makes the role clear: `Transfer(var sourceAccountId, var destinationAccountId, var amountVnd)`. If the explicit type provides important reading context, writing the type is also good. `var` only infers the type; it cannot decide domain meaning on the programmer's behalf.

## 15. Pre-Review or Pre-Merge Checklist

- [ ] Pattern variables use clear `lowerCamelCase` names appropriate to the type and domain.
- [ ] Two values of the same type with different roles have distinguishable names.
- [ ] Names in record patterns match the **component order**, especially for IDs, amounts, and addresses.
- [ ] Names do not assert states like `validated`, `paid`, or `approved` unless proven by the program.
- [ ] Currency, time, and quantity units are clear in the variable name or data type.
- [ ] `when` guards and pattern variable scopes are used properly without referencing variables outside flow scope.
- [ ] Names are used consistently across `switch` branches with the same business meaning.
- [ ] Refactorings update both declarations and references without creating duplicate names in scope.
- [ ] Examples, logs, and error messages use the right domain identifiers (`orderId` vs. `paymentId`).

## 16. References

- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): syntax of type patterns, record patterns, and pattern variables.
- [Java Language Specification 21, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): flow scoping of pattern variables.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstructing records and extracting values from components in Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): patterns in `switch`, `when`, and variable scope.
- [Oracle Java Code Conventions (historical)](https://www.oracle.com/java/technologies/javase/codeconventions-namingconventions.html): reference for `lowerCamelCase` naming style; specific domain vocabulary is decided by the development team.
