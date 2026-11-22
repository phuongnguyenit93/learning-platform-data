# Java Pattern Matching Summary Mini Project: ShopFlow Checkout (Java 21)

## 1. Context of the Capstone Practice Project

Imagine you are building a **ShopFlow Checkout** service for a small store. The system receives one of two command types:

- **Checkout:** Calculates the order amount, determines the accepted shipping/payment method, and applies a promotion in a specific case.
- **Cancel:** Accepts a cancellation request with a valid order ID (without performing an actual cancellation operation against a database).

In Checkout, the data is not flat: a `Cart` contains `Customer`, `Shipment`, `Payment`, quantity, and unit price. `Customer` in turn contains `Contact`. `Shipment` has two subtypes, `Standard`/`Express`; `Payment` has two subtypes, `Card`/`Cash`.

This is a **capstone mini project concluding the Java Core Pattern Matching section**, synthesizing what you have learned about:

- `instanceof` type patterns and flow scoping.
- `record`, record components, and nested record patterns.
- `sealed interface` and `permits` lists.
- Pattern matching in `switch` expressions.
- `when` guards, case ordering, dominance, and exhaustive checking.
- `case null`, null components, null nested records, and fallbacks.
- Sealed hierarchy results, separating domain decisions from display formatting.
- Input validation, integer-based currency, and overflow checking.
- A repeatable test suite, analyzing `javac` diagnostics, and extending subtypes.

The lesson prioritizes a **standalone runnable program** rather than a collection of disconnected snippets. The main code uses **Java 21**, where record patterns (JEP 440) and pattern matching for switch (JEP 441) are finalized features, **requiring no `--enable-preview`**.

### What You Will Be Able to Do

After completing this project, you will be able to read a `switch` expression containing multiple nested record patterns, add new cases to a sealed hierarchy yourself, design guards that do not throw `NullPointerException`, understand why a fallback can mask a missing nested subtype, and test logic before bringing it into a real system.

**Business scope of the demo:** We only **calculate quotes and make decisions**—we do not create orders in a DB, process payments, cancel transactions, or send requests to shipping carriers. Strings like `APPROVED` or `CANCEL_ACCEPTED` mean the decision at the demo layer has been accepted, **not** that an external system has executed it successfully.

## 2. Mini Project Requirements

### 2.1. Command Model

```text
Command (sealed)
├── Checkout(cart)
│   └── Cart(customer, shipment, payment, quantity, unitPriceCents)
│       ├── Customer(customerId, contact)
│       │   └── Contact(email)
│       ├── Shipment (sealed)
│       │   ├── Standard(zone)
│       │   └── Express(zone)
│       └── Payment (sealed)
│           ├── Card(last4)
│           └── Cash()
└── Cancel(orderId)
```

Each command is handled according to a clear contract:

- `null` command → rejected with code `NO_COMMAND`.
- `Cancel` with missing `orderId` or whitespace only → `INVALID_CANCEL_ID`.
- Valid `Cancel` → `CancellationAccepted` result.
- `Checkout` with a null cart → `MISSING_CART`.
- Cart missing customer/shipment/payment, non-positive quantity, or non-positive unit price → `INVALID_CART`.
- Customer with a null or blank ID → `INVALID_CUSTOMER`.
- If a required **nested record** is missing, e.g., `Customer.contact == null` → `INCOMPLETE_DETAILS`.
- Express shipping is only accepted when Payment is Card.
- Standard shipping accepts both Card and Cash.
- Express/Card, quantity 10 or more, non-null/non-blank email → **10% discount on the item subtotal**.
- Flat shipping fee by shipping type: **Express 500 cents**, **Standard 100 cents**.
- All total amount calculations must check for overflow; do not silently wrap when numbers are too large.

`Cents` in this example is the smallest integer unit (1/100 of a hypothetical currency unit). This approach avoids using `double` for adding/subtracting money. Tax policies, exchange rates, currency rounding, and carrier pricing are outside the scope of this mini project.

### 2.2. Domain Result

Instead of returning an arbitrary `String` from every branch, we define **a sealed result hierarchy**:

```text
Result (sealed)
├── Approved(rule, subtotalCents, discountCents, shippingCents, payableCents)
├── Rejected(code)
└── CancellationAccepted(orderId)
```

The result types separate **business decisions** from **stdout string formatting**. The `decide(Command)` method returns `Result`; the `display(Result)` method formats it into a structured string such as `APPROVED:STANDARD_CARD:500`.

`Result` is also a sealed type, so `display` can use an exhaustive `switch`, allowing the compiler to remind you to update it when a new result subtype is added.

## 3. Why Java 21 and Which Features Are Used?

| Feature | Role in the mini project | Where demonstrated |
| --- | --- | --- |
| `sealed interface` | Restricts command/output/shipping/payment variants | `Command`, `Shipment`, `Payment`, `Result` |
| `record` | Concise data model with typed components | `Cart`, `Customer`, `Contact`, `Card` |
| Record pattern | Binds components by declaration | `Cancel(String id)` |
| Nested record pattern | Drills down from Checkout → Cart → Customer/Shipment/Payment | Branches in `decide` |
| `var` pattern | Binds component values without deep deconstruction | `Checkout(var cart)` |
| `when` guard | Selects rules by quantity, email, and values | Express bulk, invalid input |
| Pattern `switch` expression | Selects a result via clear rules | `decide`, `display` |
| `instanceof` type pattern | Checks/binds an approved result | `isBillable` |
| `case null` | Null selector policy | `decide` and `display` |
| Exhaustiveness | Warns when a direct sealed subtype lacks a covering case | Both switch expressions |
| Compact constructor | Protects `Card` record invariants | `Card` |
| `Math.multiplyExact`/`addExact` | Catches monetary arithmetic overflow | `quote` |

**Distinguishing Java milestones:** `record` was finalized in Java 16; `sealed` was finalized in Java 17; however, **record patterns and pattern switch with `when` were finalized in Java 21**. Therefore, compile the demo with `--release 21`.

Not every use case should use a large `switch`. This example intentionally focuses on the **data classification** capability of pattern matching. If payment rules grow increasingly complex, part of the behavior can be moved into a separate domain service.

## 4. Pipeline Design: From Command to Result

```text
Command input
    |
    v
decide(Command)
    |
    +-- Check null / missing required data
    |
    +-- Match sealed subtype
    |
    +-- Deconstruct nested Cart records
    |
    +-- Apply guard when and policy rules
    |
    +-- quote(...) using exact integer arithmetic
    |
    v
Result (Approved / Rejected / CancellationAccepted)
    |
    +-- display(Result)      [switch + record pattern]
    |
    +-- isBillable(Result)   [instanceof type pattern]
    |
    v
Deterministic output + tests
```

**Note on purity:** `decide` and `quote` in the demo do not access the network, database, or filesystem. They produce a `Result` purely from input data. This makes the `switch` cases easier to test and reason about compared to code that matches patterns while simultaneously updating a DB.

The `quote` method is a **pricing helper**; it does not redo type matching itself. Each branch passes a stable `rule`, shipping fee, and specific discount rate. This organization avoids duplicating `Math.multiplyExact` across multiple cases.

## 5. Design Decisions Before Coding

### 5.1. Sealed Domain Types

We use:

```java
sealed interface Command permits Checkout, Cancel {}
sealed interface Shipment permits Standard, Express {}
sealed interface Payment permits Card, Cash {}
sealed interface Result permits Approved, Rejected, CancellationAccepted {}
```

The implementing records are implicitly `final`, so the compiler understands the controlled set of variants. If a subtype is added later, places using pattern switches may need to be updated.

**It does not implicitly allow arbitrary plugins** to create `Payment` subtypes; if the system requires third-party extensibility, `non-sealed` or another extension point may be needed, and the handling policy would differ.

### 5.2. One Clear Rule per Branch

Example `rule` codes:

- `EXPRESS_BULK_CARD`.
- `EXPRESS_CARD`.
- `STANDARD_CARD`.
- `STANDARD_CASH`.

Example `Rejected.code` values include `INVALID_CART`, `EXPRESS_CARD_ONLY`, and `AMOUNT_OVERFLOW`.

Static codes are easier to test and use as observability labels than trying to print the entire `Cart`, especially when it contains data like email addresses and payment details.

### 5.3. Money as `long`, Not `double`

Each `Cart` holds `int quantity` and `long unitPriceCents`. Calculations:

\[
\text{subtotal} = \text{quantity}\times\text{unitPriceCents}
\]

\[
\text{discount} =
\begin{cases}
\left\lfloor \frac{\text{subtotal}}{10}\right\rfloor, & \text{if }10\%\text{ discount}\\
0, & \text{if no discount}
\end{cases}
\]

\[
\text{payable} = \text{subtotal}-\text{discount}+\text{shipping}.
\]

In the demo, integer division truncates (rounds down) to whole cents for the 10% discount. This is **the rounding rule for the example**, not a universal financial rule for every market. Production systems need consistent rounding, tax, refund, and currency unit policies.

To guard against overflow, use `Math.multiplyExact`, `Math.subtractExact`, and `Math.addExact` instead of operators that silently wrap. When an amount cannot be represented as a `long`, return `Rejected("AMOUNT_OVERFLOW")`.

### 5.4. Invariant for `Card`

The `Card` record only stores four simulated last digits. It checks for **exactly four ASCII characters from 0 to 9**. This is not full payment card validation and is strictly **not a place to store PAN/CVV**. For real systems, use tokenized payment instruments and appropriate security standards.

In the demo, other records do not have comprehensive constructor validation so learners can practice writing guards and fallbacks for invalid data. This is a **pedagogical choice**, not an endorsement of allowing `Customer.contact == null` in a production domain model.

## 6. Complete Java 21 Program

Create a file named **`PatternCheckoutMiniProject.java`** with the following content. All types are nested inside a single public class so it can be easily run with a single `javac` command; no Maven, Gradle, or framework is required.

```java
import java.util.Objects;

public class PatternCheckoutMiniProject {
    sealed interface Command permits Checkout, Cancel {}
    record Checkout(Cart cart) implements Command {}
    record Cancel(String orderId) implements Command {}

    record Cart(Customer customer, Shipment shipment, Payment payment,
                int quantity, long unitPriceCents) {}
    record Customer(String customerId, Contact contact) {}
    record Contact(String email) {}

    sealed interface Shipment permits Standard, Express {}
    record Standard(String zone) implements Shipment {}
    record Express(String zone) implements Shipment {}

    sealed interface Payment permits Card, Cash {}
    record Card(String last4) implements Payment {
        Card {
            if (last4 == null || !last4.matches("[0-9]{4}")) {
                throw new IllegalArgumentException(
                    "last4 must be four digits");
            }
        }
    }
    record Cash() implements Payment {}

    sealed interface Result
            permits Approved, Rejected, CancellationAccepted {}

    record Approved(
            String rule, long subtotalCents, long discountCents,
            long shippingCents, long payableCents) implements Result {}

    record Rejected(String code) implements Result {}
    record CancellationAccepted(String orderId) implements Result {}

    static Result quote(
            String rule, int quantity, long unitPriceCents,
            long shippingCents, int discountPercent) {
        try {
            long subtotal =
                Math.multiplyExact((long) quantity, unitPriceCents);

            long discount =
                discountPercent == 10 ? subtotal / 10 : 0;

            long payable = Math.addExact(
                Math.subtractExact(subtotal, discount),
                shippingCents);

            return new Approved(
                rule, subtotal, discount, shippingCents, payable);

        } catch (ArithmeticException overflow) {
            return new Rejected("AMOUNT_OVERFLOW");
        }
    }

    static Result decide(Command command) {
        return switch (command) {
            case null ->
                new Rejected("NO_COMMAND");

            case Cancel(String id) when id == null || id.isBlank() ->
                new Rejected("INVALID_CANCEL_ID");
            case Cancel(String id) ->
                new CancellationAccepted(id);

            case Checkout(var cart) when cart == null ->
                new Rejected("MISSING_CART");

            case Checkout(Cart(
                    var customer, var shipment, var payment,
                    int quantity, long unitPrice))
                    when customer == null || shipment == null ||
                         payment == null || quantity <= 0 ||
                         unitPrice <= 0 ->
                new Rejected("INVALID_CART");

            case Checkout(Cart(
                    Customer(String id, var contact),
                    var shipment, var payment,
                    int quantity, long unitPrice))
                    when id == null || id.isBlank() ->
                new Rejected("INVALID_CUSTOMER");

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Express(String zone), Card(String last4),
                    int quantity, long unitPrice))
                    when quantity >= 10 && email != null &&
                         !email.isBlank() ->
                quote(
                    "EXPRESS_BULK_CARD",
                    quantity, unitPrice, 500, 10);

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Express(String zone), Card(String last4),
                    int quantity, long unitPrice)) ->
                quote(
                    "EXPRESS_CARD",
                    quantity, unitPrice, 500, 0);

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Express(String zone), Cash(),
                    int quantity, long unitPrice)) ->
                new Rejected("EXPRESS_CARD_ONLY");

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Standard(String zone), Card(String last4),
                    int quantity, long unitPrice)) ->
                quote(
                    "STANDARD_CARD",
                    quantity, unitPrice, 100, 0);

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Standard(String zone), Cash(),
                    int quantity, long unitPrice)) ->
                quote(
                    "STANDARD_CASH",
                    quantity, unitPrice, 100, 0);

            case Checkout(var cart) ->
                new Rejected("INCOMPLETE_DETAILS");
        };
    }

    static String display(Result result) {
        return switch (result) {
            case Approved(
                    String rule, long base, long discount,
                    long shipping, long payable)
                    when discount > 0 ->
                "APPROVED_PROMO:" + rule + ":" + payable;

            case Approved(
                    String rule, long base, long discount,
                    long shipping, long payable) ->
                "APPROVED:" + rule + ":" + payable;

            case Rejected(String code) ->
                "REJECTED:" + code;

            case CancellationAccepted(String id) ->
                "CANCEL_ACCEPTED:" + id;

            case null ->
                "NO_RESULT";
        };
    }

    static boolean isBillable(Result result) {
        return result instanceof Approved approved &&
               approved.payableCents() > 0;
    }

    static int passed;

    static void check(
            String testId, Command command,
            String expected, boolean expectedBillable) {
        Result result = decide(command);
        String actual = display(result);
        boolean billable = isBillable(result);

        if (!Objects.equals(actual, expected) ||
                billable != expectedBillable) {
            throw new AssertionError(
                testId + " expected " + expected + "/" +
                expectedBillable + " but got " +
                actual + "/" + billable);
        }

        passed++;
        System.out.println(
            testId + " " + actual + " | billable=" + billable);
    }

    static void expectBadCard() {
        try {
            new Card("ABC");
            throw new AssertionError("Expected invalid Card");
        } catch (IllegalArgumentException expected) {
            passed++;
            System.out.println("C20 CARD_INVALID");
        }
    }

    public static void main(String[] args) {
        Customer lan =
            new Customer("U1", new Contact("lan@example.test"));
        Customer noEmail =
            new Customer("U2", new Contact(null));

        Shipment express = new Express("NORTH");
        Shipment standard = new Standard("SOUTH");
        Payment card = new Card("1234");
        Payment cash = new Cash();

        check("C01", null,
            "REJECTED:NO_COMMAND", false);
        check("C02", new Cancel(null),
            "REJECTED:INVALID_CANCEL_ID", false);
        check("C03", new Cancel("ORD-7"),
            "CANCEL_ACCEPTED:ORD-7", false);
        check("C04", new Checkout(null),
            "REJECTED:MISSING_CART", false);

        check("C05", new Checkout(new Cart(
            null, express, card, 1, 200)),
            "REJECTED:INVALID_CART", false);

        check("C06", new Checkout(new Cart(
            lan, express, card, 0, 200)),
            "REJECTED:INVALID_CART", false);

        check("C07", new Checkout(new Cart(
            lan, express, card, 2, -1)),
            "REJECTED:INVALID_CART", false);

        check("C08", new Checkout(new Cart(
            new Customer(" ", new Contact("x@example.test")),
            express, card, 2, 200)),
            "REJECTED:INVALID_CUSTOMER", false);

        check("C09", new Checkout(new Cart(
            lan, express, card, 2, 200)),
            "APPROVED:EXPRESS_CARD:900", true);

        check("C10", new Checkout(new Cart(
            lan, express, card, 10, 200)),
            "APPROVED_PROMO:EXPRESS_BULK_CARD:2300", true);

        check("C11", new Checkout(new Cart(
            noEmail, express, card, 10, 200)),
            "APPROVED:EXPRESS_CARD:2500", true);

        check("C12", new Checkout(new Cart(
            lan, express, cash, 2, 200)),
            "REJECTED:EXPRESS_CARD_ONLY", false);

        check("C13", new Checkout(new Cart(
            lan, standard, card, 2, 200)),
            "APPROVED:STANDARD_CARD:500", true);

        check("C14", new Checkout(new Cart(
            lan, standard, cash, 3, 200)),
            "APPROVED:STANDARD_CASH:700", true);

        check("C15", new Checkout(new Cart(
            new Customer("U3", null),
            express, card, 2, 200)),
            "REJECTED:INCOMPLETE_DETAILS", false);

        check("C16", new Checkout(new Cart(
            lan, null, card, 2, 200)),
            "REJECTED:INVALID_CART", false);

        check("C17", new Checkout(new Cart(
            lan, standard, card, 2, Long.MAX_VALUE)),
            "REJECTED:AMOUNT_OVERFLOW", false);

        check("C18", new Checkout(new Cart(
            lan, standard, null, 2, 200)),
            "REJECTED:INVALID_CART", false);

        check("C19", new Checkout(new Cart(
            lan, standard, card, 1, Long.MAX_VALUE)),
            "REJECTED:AMOUNT_OVERFLOW", false);

        expectBadCard();

        System.out.println("RESULT_NULL=" + display(null));
        System.out.println("TESTS=" + passed);
    }
}
```

### Compiling and Running

**JDK 21 or later** is required. Navigate to the directory containing the file and run:

```bash
javac --release 21 PatternCheckoutMiniProject.java
java PatternCheckoutMiniProject
```

The program requires no external dependencies. The test suite throws an explicit `AssertionError` on failure, so `java -ea` is not needed.

### Exact Stdout

```text
C01 REJECTED:NO_COMMAND | billable=false
C02 REJECTED:INVALID_CANCEL_ID | billable=false
C03 CANCEL_ACCEPTED:ORD-7 | billable=false
C04 REJECTED:MISSING_CART | billable=false
C05 REJECTED:INVALID_CART | billable=false
C06 REJECTED:INVALID_CART | billable=false
C07 REJECTED:INVALID_CART | billable=false
C08 REJECTED:INVALID_CUSTOMER | billable=false
C09 APPROVED:EXPRESS_CARD:900 | billable=true
C10 APPROVED_PROMO:EXPRESS_BULK_CARD:2300 | billable=true
C11 APPROVED:EXPRESS_CARD:2500 | billable=true
C12 REJECTED:EXPRESS_CARD_ONLY | billable=false
C13 APPROVED:STANDARD_CARD:500 | billable=true
C14 APPROVED:STANDARD_CASH:700 | billable=true
C15 REJECTED:INCOMPLETE_DETAILS | billable=false
C16 REJECTED:INVALID_CART | billable=false
C17 REJECTED:AMOUNT_OVERFLOW | billable=false
C18 REJECTED:INVALID_CART | billable=false
C19 REJECTED:AMOUNT_OVERFLOW | billable=false
C20 CARD_INVALID
RESULT_NULL=NO_RESULT
TESTS=20
```

`TESTS=20` is the sum of **19 `check` cases** plus one validation case in `expectBadCard`. The `RESULT_NULL` line demonstrates the null formatting policy and does not increment the test counter.

## 7. Tracing `decide`: Why Were the Cases Chosen This Way?

### 7.1. Null Selector Before Any Command Type

```java
case null -> new Rejected("NO_COMMAND");
```

A null selector in a pattern `switch` should be handled according to policy. `case null` is clearer than assuming `default` acts as a catch-all for null. If the contract requires null to be a programming error rather than a rejected result, you can validate at the boundary and throw `NullPointerException` or an appropriate exception.

### 7.2. Specific Type, Guard, Then Unguarded Case

For `Cancel`:

```java
case Cancel(String id) when id == null || id.isBlank() ->
    new Rejected("INVALID_CANCEL_ID");

case Cancel(String id) ->
    new CancellationAccepted(id);
```

Both cases match the `Cancel` subtype. The guarded first case catches null/blank IDs; the unguarded second case handles all remaining `Cancel` instances. If the order were reversed, the guarded case would be **dominated** by the first case and rejected by the compiler.

`id == null || id.isBlank()` relies on short-circuit evaluation; when `id` is null, Java does not call `isBlank()`.

### 7.3. Using `var` to Check Null Components

```java
case Checkout(var cart) when cart == null ->
    new Rejected("MISSING_CART");
```

`Checkout` is a non-null record; its `cart` component may be null. `var cart` binds even a null value so the guard can inspect it. Conversely, if you wrote `Checkout(Cart(...))`, a `cart == null` would not match the **nested record pattern** `Cart(...)`.

Next:

```java
case Checkout(Cart(
        var customer, var shipment, var payment,
        int quantity, long unitPrice))
        when customer == null || shipment == null ||
             payment == null || quantity <= 0 || unitPrice <= 0 ->
    new Rejected("INVALID_CART");
```

This is an example of **nested record patterns + `var` patterns + guard**. `Cart(...)` only matches when `Cart` exists; the inner components are bound, including null for reference types. The guard checks all these business conditions in one place.

### 7.4. Validating Customer ID Without Requiring Contact to Exist

```java
case Checkout(Cart(
        Customer(String id, var contact),
        var shipment, var payment,
        int quantity, long unitPrice))
        when id == null || id.isBlank() ->
    new Rejected("INVALID_CUSTOMER");
```

By using `var contact`, this rule still matches a `Customer` with a null contact so it can validate the ID. A deeper pattern `Customer(String id, Contact(String email))` would fail to match if `contact` is null, potentially skipping the ID error.

This illustrates an important principle: **the depth of a pattern determines which cases can reach the guard**. Do not nest every record to the deepest level just because the syntax allows it; nest only as deep as needed for the rule being checked.

### 7.5. Express/Card: Bulk Guard Before Regular Branch

```java
case Checkout(Cart(
        Customer(String id, Contact(String email)),
        Express(String zone), Card(String last4),
        int quantity, long unitPrice))
        when quantity >= 10 && email != null &&
             !email.isBlank() ->
    quote("EXPRESS_BULK_CARD", quantity, unitPrice, 500, 10);
```

The pattern requires:
- Command is `Checkout`.
- `Cart` is non-null.
- `Customer` is non-null and has a non-null `Contact`.
- Shipment is `Express`.
- Payment is `Card`.
- Quantity and unit price are the `int`/`long` values of `Cart`.

The guard additionally requires a large quantity and a non-blank email. If true, a 10% discount is applied.

The **unguarded** Express/Card case immediately follows for regular pricing:

```java
case Checkout(Cart(
        Customer(String id, Contact(String email)),
        Express(String zone), Card(String last4),
        int quantity, long unitPrice)) ->
    quote("EXPRESS_CARD", quantity, unitPrice, 500, 0);
```

This ordering has business significance: the bulk case comes first, and the remaining card cases follow. If the general case were placed first, the compiler would report a **dominated case**.

### 7.6. Express/Cash Rejected

```java
case Checkout(Cart(
        Customer(String id, Contact(String email)),
        Express(String zone), Cash(),
        int quantity, long unitPrice)) ->
    new Rejected("EXPRESS_CARD_ONLY");
```

`Cash()` is a record pattern for a record with no components. Do not write `Cash` as a type pattern with a variable if the goal here is to deconstruct the exact subtype. Under the demo policy, Express does not accept Cash, so `quote` is not called.

This helps distinguish **whether a pattern matches structurally** from **whether the business rule accepts it**. The Express/Cash pattern matches successfully, yet the `Result` is `Rejected`.

### 7.7. Standard Accepts Both Payment Types

The Standard/Card and Standard/Cash cases share the same 100-cent shipping fee and no discount. They are kept separate in `switch` so learners can clearly see classification across both sealed subtypes of `Payment`.

If a production system has many `Payment` types, listing every shipment/payment pair may no longer be structurally optimal. In that case, consider extracting fee tables and corresponding policies into domain services while keeping pattern matching where classification adds real value.

### 7.8. Fallback for Incomplete Nested Data

```java
case Checkout(var cart) ->
    new Rejected("INCOMPLETE_DETAILS");
```

This case catches all remaining `Checkout` instances, including:

```java
new Checkout(new Cart(
    new Customer("U3", null),
    new Express("NORTH"), new Card("1234"), 2, 200))
```

`Customer` exists, but `Customer.contact == null`, so the nested `Contact(String email)` in the specific cases **does not match**. The fallback case catches the command and returns `INCOMPLETE_DETAILS`.

**Place the fallback last:** If the general `Checkout` case appeared before Card/Cash, the specific cases after it would be dominated. The fallback makes the `switch` cover every `Checkout`, but with a trade-off: when adding a new `Shipment`/`Payment` subtype without adding a corresponding case, the fallback can still return `INCOMPLETE_DETAILS` even though the new data is completely valid. Therefore, **compiler exhaustiveness on `Command` does not replace tests for the nested `Payment`/`Shipment` hierarchies**.

## 8. The `quote` Method: Separating Business Calculation from Type Matching

`quote` receives the selected rule along with quantity, unit price, shipping fee, and discount rate:

```java
static Result quote(String rule, int quantity, long unitPriceCents,
                    long shippingCents, int discountPercent) {
    try {
        long subtotal = Math.multiplyExact(
            (long) quantity, unitPriceCents);
        long discount = discountPercent == 10
            ? subtotal / 10 : 0;
        long payable = Math.addExact(
            Math.subtractExact(subtotal, discount),
            shippingCents);

        return new Approved(
            rule, subtotal, discount, shippingCents, payable);
    } catch (ArithmeticException ex) {
        return new Rejected("AMOUNT_OVERFLOW");
    }
}
```

**Why not perform all arithmetic directly in each case?** That would duplicate overflow handling and pricing structure. If the arithmetic rules change, you would have to update multiple branches, risking divergence.

**Why use `exact` arithmetic?** With integers, multiplication/addition can overflow and wrap around, producing an incorrect payable amount. `Math.multiplyExact`/`Math.addExact`/`Math.subtractExact` throw `ArithmeticException` instead of returning a wrapped result. The helper translates this arithmetic error into `Rejected("AMOUNT_OVERFLOW")`.

**Limitations:** The helper only accepts `discountPercent` values of 0 or 10 as used by the call sites in the demo. This is not yet a general-purpose pricing API; for production, validate `discountPercent`, `shippingCents`, and other invariants directly. When business requirements need amounts exceeding `long` range, consider `BigInteger`/`BigDecimal` or an appropriate domain `Money` type.

### Two Overflow Tests

- **C17:** quantity = 2, unitPriceCents = `Long.MAX_VALUE` → `Math.multiplyExact` overflows.
- **C19:** quantity = 1, unitPriceCents = `Long.MAX_VALUE` → subtotal does not overflow, but adding 100 cents for shipping causes `Math.addExact` to overflow.

Both return `REJECTED:AMOUNT_OVERFLOW`, showing that not only multiplication but also the final addition must be guarded.

## 9. Sealed `Result` + Second Pattern Switch

`decide` returns one of three subtypes of `Result`:

```java
sealed interface Result
    permits Approved, Rejected, CancellationAccepted {}

record Approved(String rule, long subtotalCents, long discountCents,
                long shippingCents, long payableCents) implements Result {}

record Rejected(String code) implements Result {}
record CancellationAccepted(String orderId) implements Result {}
```

`display` is **another operation** over the same result model. It uses a guard to distinguish an `Approved` result with a discount:

```java
case Approved(String rule, long base, long discount,
              long shipping, long payable)
        when discount > 0 ->
    "APPROVED_PROMO:" + rule + ":" + payable;

case Approved(String rule, long base, long discount,
              long shipping, long payable) ->
    "APPROVED:" + rule + ":" + payable;
```

Here:
- The record pattern directly deconstructs `Approved`.
- The `discount > 0` guard must precede the unguarded `Approved` case.
- `Rejected` and `CancellationAccepted` are handled separately.
- `case null` defines how a null result is displayed.
- No `default` is needed when every direct permitted subtype is covered.

**Exhaustiveness in two places:** Adding a new subtype of `Result` causes `display` to report non-exhaustiveness. Adding a new subtype of `Command` causes `decide` to report non-exhaustiveness. These are two distinct safeguards corresponding to **input** and **output**.

The compiler does not check whether the string `APPROVED_PROMO` matches marketing intent; that is the job of tests and contracts.

## 10. Type Pattern with `instanceof` and Flow Scoping

Not every operation needs a `switch`. When asking a simple boolean question, an `instanceof` type pattern is a great fit:

```java
static boolean isBillable(Result result) {
    return result instanceof Approved approved &&
           approved.payableCents() > 0;
}
```

`approved` can only be used on the right-hand side of `&&` after the `instanceof` check succeeds. This is **flow scoping**: Java allows reading a pattern variable wherever the condition has proven it is definitely bound.

- If `result` is `Approved` and payable > 0, return true.
- If `result` is `Rejected` or `CancellationAccepted`, return false.
- If `result` is null, `instanceof` evaluates to false, so `approved` is never dereferenced.

An older style required `instanceof Approved` followed by a cast, whereas the pattern eliminates manual casting from the source. There is no need to argue performance from "fewer lines"—the primary benefit here is clarity and type safety.

### Variable Scope Does Not Extend Arbitrarily

An intentionally invalid snippet:

```java
// Not part of the runnable program.
if (result instanceof Approved approved) {
    System.out.println(approved.rule());
}
System.out.println(approved.rule()); // variable is out of scope here
```

A pattern variable is not a local variable declared for the entire method. If you need a value outside the branch, design the variable/result properly or use a `switch` expression that returns a value.

## 11. 20-Case Test Matrix

All 20 cases in the program are compared against expected output, and the `check` cases also verify `isBillable` against the contract.

| Test | Scenario | Primary expectation |
| --- | --- | --- |
| C01 | Null command | `REJECTED:NO_COMMAND` |
| C02 | Null cancel ID | `REJECTED:INVALID_CANCEL_ID` |
| C03 | Valid cancel ID | `CANCEL_ACCEPTED:ORD-7` |
| C04 | Checkout with null cart | `REJECTED:MISSING_CART` |
| C05 | Cart with null customer | `REJECTED:INVALID_CART` |
| C06 | Quantity equal to 0 | `REJECTED:INVALID_CART` |
| C07 | Negative unitPrice | `REJECTED:INVALID_CART` |
| C08 | Blank customer ID | `REJECTED:INVALID_CUSTOMER` |
| C09 | Express/Card, quantity 2 | `APPROVED:EXPRESS_CARD:900` |
| C10 | Express/Card, quantity 10, with email | `APPROVED_PROMO:EXPRESS_BULK_CARD:2300` |
| C11 | Express/Card, quantity 10, null email | `APPROVED:EXPRESS_CARD:2500` |
| C12 | Express/Cash | `REJECTED:EXPRESS_CARD_ONLY` |
| C13 | Standard/Card, quantity 2 | `APPROVED:STANDARD_CARD:500` |
| C14 | Standard/Cash, quantity 3 | `APPROVED:STANDARD_CASH:700` |
| C15 | Null Contact record | `REJECTED:INCOMPLETE_DETAILS` |
| C16 | Null shipment | `REJECTED:INVALID_CART` |
| C17 | Overflow on multiplication | `REJECTED:AMOUNT_OVERFLOW` |
| C18 | Null payment | `REJECTED:INVALID_CART` |
| C19 | Overflow on adding shipping fee | `REJECTED:AMOUNT_OVERFLOW` |
| C20 | Card with `last4="ABC"` | `IllegalArgumentException` caught by test |

The tests are written in plain Java SE; in a real project they can be migrated to JUnit 5 parameterized tests. Regardless of the framework, **expected values must reflect business requirements**, not merely mirror the output of the function under test.

### Verifying a Pricing Example

For **C10**: quantity 10, unitPrice 200 cents, Express fee 500 cents:
- Subtotal = 10 × 200 = 2,000 cents.
- Discount 10% = 200 cents.
- Shipping = 500 cents.
- Payable = 2,000 − 200 + 500 = **2,300 cents**.

Thus, the output `APPROVED_PROMO:EXPRESS_BULK_CARD:2300` is consistent. C09 with quantity 2 receives no discount, has subtotal 400 and Express fee 500 → payable 900.

### Important Boundary Values

The bulk guard uses `quantity >= 10`. Both **9 and 10** should have tests when expanding the exercise to catch off-by-one bugs like writing `> 10` instead of `>= 10` or vice versa. The demo currently tests quantity 2 and quantity 10; testing 10 protects the threshold itself, while adding 9 increases confidence just below the threshold.

For `unitPriceCents` and `quantity`, the `<= 0` condition should test both 0 and negative numbers in a full suite. For `Card.last4`, also test null, 3/5-digit strings, and non-ASCII digits if a real API receives external input.

### True/False Results of `isBillable`

`isBillable` does not use string matching on `display`. It inspects the actual type of `Result` and the `payableCents` value. That is useful when changing display messages without altering business logic.

In the suite, cases C09, C10, C11, C13, and C14 return true. Rejected/CancellationAccepted cases return false. `isBillable(null)` also returns false because `instanceof` on null does not match.

## 12. Null Policy and Nested Records: Common Misconceptions

There are multiple levels of null in the mini project:

| Location | Example | Result |
| --- | --- | --- |
| Selector of `decide` | `decide(null)` | `NO_COMMAND` |
| Component `Checkout.cart` | `new Checkout(null)` | `MISSING_CART` |
| Component `Cart.customer` | `new Cart(null, ...)` | `INVALID_CART` |
| Component `Cart.shipment` | Null Shipment | `INVALID_CART` |
| Component `Cart.payment` | Null Payment | `INVALID_CART` |
| Component `Customer.contact` | `new Customer("U3", null)` | `INCOMPLETE_DETAILS` |
| Component `Contact.email` | `new Contact(null)` | `Contact` pattern can still match; no promo |
| Selector of `display` | `display(null)` | `NO_RESULT` |

### Null Selector vs. Null Component

`case null` in `switch (command)` handles a **null command**, not every deeply nested null component. A nested record pattern `Contact(String email)` requires the **`Contact` record to exist**, though the `email` component itself may be null. A `var contact` can bind null because it does not require matching a specific nested record.

This is why the code handles invalid cases at appropriate levels **before** using deep patterns. If you place too many nested constraints in a validation case, an invalid object might fail to match the case meant to report the error.

### Fallback Does Not Mean "Catching Exceptions"

`case Checkout(var cart) -> new Rejected("INCOMPLETE_DETAILS")` is selected if earlier patterns do not match or their guards evaluate to false. It does **not** automatically catch exceptions thrown by an accessor, body, or guard.

If a custom record accessor throws an exception during deconstruction, Java 21 has rules involving `MatchException` wrapping the underlying cause. If a guard throws `NullPointerException`, the exception does not silently turn into a false guard. Handle errors at the appropriate boundary rather than assuming the fallback case will always run.

### Early Validation vs. Pattern Validation

The demo intentionally allows `Cart.quantity <= 0` to be constructed and then returns `Rejected`. For a stricter domain, you can validate in the compact constructor:

```java
// Alternative illustrative definition; do not place alongside Cart in the main code.
record Cart(Customer customer, Shipment shipment, Payment payment,
            int quantity, long unitPriceCents) {
    Cart {
        Objects.requireNonNull(customer);
        Objects.requireNonNull(shipment);
        Objects.requireNonNull(payment);
        if (quantity <= 0 || unitPriceCents <= 0) {
            throw new IllegalArgumentException("invalid cart");
        }
    }
}
```

In that setup, some invalid cases in the `switch` will never receive malformed objects because the constructor already rejected them. Both policies can make sense depending on the data layer: an **input DTO** accepts bad data to return validation errors; a **domain value object** should enforce invariants. Do not mix these two responsibilities accidentally.

## 13. Compiler Feedback When Extending the System

### 13.1. Adding a New `Command`

Suppose we add:

```java
// Extension illustration; do not add to the runnable file without updating permits/cases.
record Track(String orderId) implements Command {}
```

You must update `Command`'s `permits` clause to include `Track`. When the compiler rebuilds `decide`, no case currently handles `Track`; thus you get the diagnostic:

```text
the switch expression does not cover all possible input values
```

**Right action:** Decide the contract for `Track`, add a case for `Track`, and write tests, instead of adding `default -> new Rejected("OTHER")` to bypass updating.

### 13.2. Dominance When Placing a General Case First

If you write:

```java
// INTENTIONALLY INVALID in the same switch:
case Cart(int quantity) -> "STANDARD";
case Cart(int quantity) when quantity >= 10 -> "BULK";
```

This snippet only illustrates the idea. The real `Cart` in the program has **five** components, so a single-component pattern would trigger an arity error before dominance is even checked. To reproduce dominance accurately, use a simpler record:

```java
// Separate illustrative snippet:
record Line(int quantity) {}

static String classifyLine(Object line) {
    return switch (line) {
        case Line(int quantity) -> "STANDARD";
        case Line(int quantity) when quantity >= 10 -> "BULK";
        default -> "OTHER";
    };
}
```

This code is **intentionally invalid**: the unguarded case first matches every `Line`, causing the subsequent `BULK` case to be dominated. `javac` reports:

```text
this case label is dominated by a preceding case label
```

**Fix:** Place the `when quantity >= 10` case first. These two forms of compiler feedback—non-exhaustive and dominated—are distinct errors: one indicates missing coverage, while the other indicates a case shadowed by a preceding case.

Both diagnostics have been verified with `JavaCompiler` at `--release 21`.

### 13.3. Adding a New `Payment` May Not Trigger a Compiler Error

Suppose:

```java
// Hierarchy extension illustration:
record Voucher(String code) implements Payment {}
```

You update `Payment`'s `permits` list, while `decide` still has the general `Checkout(var cart)` case at the end. The compiler still considers the switch on **`Command`** exhaustive because every `Checkout` has a fallback. However, a `Cart` with a `Voucher` payment would return `INCOMPLETE_DETAILS` even when the voucher is valid.

**This is an important limitation of exhaustiveness checking:** The compiler only proves that a selector is covered by some case; it does not prove that every deeply nested subtype is handled according to business rules. When adding a new `Payment`/`Shipment` subtype, update the **nested hierarchy test matrix** rather than relying solely on a green build.

### 13.4. Adding a New `Result`

If you extend `Result` with a `Pending` subtype, the `display` method must be revisited. Because `display` has no `default`, the compiler requires adding a case to preserve exhaustiveness.

In multi-module systems, you must **recompile consumers** so the compiler sees the updated hierarchy. Building only the module containing the model cannot guarantee that all external switches have been updated.

## 14. Common Mistakes and How to Fix Them

| Mistake | Why it is problematic | How to fix |
| --- | --- | --- |
| Using `double` for money without a policy | Rounding errors, hard to control | Use cents or an explicit `Money` type |
| Using `quantity * unitPrice` and allowing overflow | Can produce negative/wrong amounts | Use `Math.multiplyExact` and `addExact` |
| Treating `Approved` as already charged | Confuses decision with execution | Separate quote/approval from payment commit |
| Using only `command.getClass()` | Cannot distinguish bulk/normal guards | Tie rule IDs to actual branches |
| Placing unguarded Express/Card before promo | Promo case gets dominated | Put guarded cases first |
| Using `case null` to catch all null components | Null selector differs from nested null | Use `var`, guards, and appropriate invariants |
| Always nesting patterns as deeply as possible | Harder to read and misses early validation | Nest only as deep as the rule needs |
| Using a broad `default` to avoid build errors | Ignores new subtypes | Keep exhaustive cases where possible |
| Assuming exhaustive `Command` covers `Payment` | Fallback can mask new `Payment` variants | Test the nested subtype matrix |
| Logging entire `Cart`/`Card` objects | May expose PII/payment info | Log allowlisted metadata, not raw records |
| Catching every `Exception` and returning `AMOUNT_OVERFLOW` | Masks non-arithmetic bugs | Catch only `ArithmeticException` around arithmetic |
| Skipping real JDK runtime tests | Compiling does not guarantee runtime compatibility | Test on the target runtime |
| Using Java 21 syntax under `--release 17` | Compiler rejects it | Upgrade target or use `instanceof` type patterns |
| Changing record structure without updating consumers | Pattern arity/types break | Build/review all dependent modules |
| Using a pattern variable out of scope | `cannot find symbol` | Respect flow scoping |
| Testing C10 without testing just below the threshold | Boundary bugs can slip through | Add quantity 9/10 tests |

## 15. Repo Structure When Growing into a Real Project

A single-file program is great for learning, but larger systems should separate responsibilities:

```text
shopflow/
  domain/
    Command.java
    Cart.java
    Customer.java
    Shipment.java
    Payment.java
    Result.java
  application/
    CheckoutDecisionService.java
    QuoteCalculator.java
  adapter/
    HttpCheckoutController.java
    CheckoutResultMapper.java
  tests/
    CheckoutDecisionServiceTest.java
    QuoteCalculatorTest.java
    CheckoutApiIntegrationTest.java
```

This is a **recommended structure**, not files you must create to run `PatternCheckoutMiniProject.java`. Principles:
- The domain model holds invariants and necessary value types.
- The application service owns rule selection flow, without mixing logging/network I/O with pattern matching.
- The calculator computes monetary amounts in one place and is tested independently.
- Adapters translate HTTP/JSON into commands and `Result` into responses; sensitive fields should not be logged by default.
- When adding a `Payment` subtype, update mappers, tests, and policies accordingly.

JUnit 5 can be used for parameterized tests, though it is an **external dependency outside the JDK**. The demo does not pretend that JUnit source can run with `javac` alone. If migrating to JUnit, keep the expected outputs, overflow cases, and null matrix in `@ParameterizedTest`/`@MethodSource`.

### Practical Testing Expansion

A production test suite should also add:
- Constructor tests with null `Card`, three digits, five digits, or non-ASCII digit characters.
- Tests for quantity 9/10, negative quantity, unitPrice 0, and blank email.
- Assertions on the `Approved` fields themselves: subtotal, discount, shipping, payable—not just the summary string.
- Tests with very large amounts, addition overflow, and multiplication overflow.
- DTO parsing tests: distinguishing missing JSON fields, JSON null, and wrong types.
- Tests ensuring email/Card details are never leaked to logs or metrics.
- Integration tests for idempotency/actual cancellation if the project adds a database/payment gateway.
- API contract and permission checks; a matching pattern does not authorize executing a command.

## 16. Must You Use Pattern Switch for Every Behavior?

No. Choose the technique based on the goal:

- Use an **`instanceof` type pattern** for a single simple condition or a short `if` pipeline.
- Use a **record pattern** when deconstructing data structures without manually calling accessors across multiple levels.
- Use a **`switch` expression** when classifying a sealed hierarchy into a `Result`, especially when you want the compiler to prompt subtype updates.
- Use **polymorphism** or a domain service when behavior naturally belongs to the domain type and is reused across many consumers.
- Use **`when` guards** for concise, null-safe conditions; if a rule is very complex, extract a pure helper and test it separately.
- Do not turn all logic into a massive `switch` with hundreds of cases if a dedicated decision table or rule engine fits better.

**Trade-off:** A sealed type closes the set of variants for compiler exhaustiveness checks. However, if a real system needs arbitrary plugins to add `Payment` or `Shipment` types, a closed design may not fit. Choose abstractions based on required extensibility, not just the syntax you want to use.

### Untrusted Data

Pattern matching is a **tool for branching on type and structure**, not an authentication/authorization mechanism. A successful record pattern match does not mean:
- The user has permission to cancel that order.
- The payment token is still valid.
- The email is a valid address.
- The quantity is in stock.
- Client-supplied prices are trustworthy to charge.

Those require domain validation, application authorization, and dedicated system integrations. This mini project intentionally stays scoped to classification/pricing so responsibilities are not mixed.

## 17. Extension Exercises for Learners

**Exercise 1 — 9/10 Guard:** Add Express/Card Checkout tests with a valid email and quantity 9 and quantity 10. Expect `EXPRESS_CARD` for 9 and `EXPRESS_BULK_CARD` for 10. Identify which test catches a `> 10` bug.

**Exercise 2 — Blank Email:** Add `new Contact("   ")` with Express/Card quantity 10. Expect no promotion applied. Explain why the guard must check `email != null` before `!email.isBlank()`.

**Exercise 3 — Voucher:** Add `Voucher(String code) implements Payment`, update `permits`, and implement the policy: only accepted with Standard, applying a flat 50-cent discount not exceeding the subtotal. Predict whether the compiler will immediately require a `Voucher` case while `Checkout(var cart)` remains at the end. Add tests.

**Exercise 4 — Same Model, New Operation:** Write `String receipt(Result)` to output a demo receipt. Use an exhaustive `switch` on `Result` without printing email or Card details. Add a `Pending` subtype and observe the compiler's response.

**Exercise 5 — Pricing Policy:** Convert `discountPercent` into an enum or value type; validate that only 0–100 is allowed. Add rounding per contract and test with prices not divisible by 10.

**Exercise 6 — Java 17 Project:** Rewrite `decide` using `instanceof` type patterns and manual record accessor calls, keeping the same expected outputs. Do not use Java 21 record patterns/switch patterns under `--release 17`.

**Exercise 7 — Zone-Based Fees:** Give Express zone `NORTH` a 500-cent fee and `SOUTH` a 700-cent fee. Design guards or a policy helper without duplicating arithmetic. Test each zone, null zone, and unsupported zone.

**Exercise 8 — Overflow Tests:** Create a case where subtotal is valid but payable overflows after adding the fee, and a case where `multiplyExact` overflows. Compare with C17/C19 and explain which step differs.

**Exercise 9 — Domain Invariant:** Move quantity and unitPrice validation into `Cart`'s compact constructor. Adjust the tests: instead of `Rejected` from `decide` for bad data, the constructor may throw `IllegalArgumentException`. Explain when to choose boundary policy versus domain invariants.

**Exercise 10 — Split Source Files:** Move records into a domain package, the decision engine into an application package, and tests into a test source set. Set up a Java 21 build pipeline and ensure adding a new subtype forces reviewing every relevant consumer.

## 18. Mini Project Completion Checklist

A self-assessment checklist after practicing:

1. Does every record pattern have the exact component count and order of its declaration?
2. Do `Command`/`Shipment`/`Payment`/`Result` have the right permitted subtypes?
3. Do `when` cases precede their corresponding unguarded cases?
4. Is a `null` selector handled separately from null components according to the contract?
5. Is `var` used only when binding a component without requiring deep deconstruction?
6. Are pattern variables used within their valid scope?
7. Does `decide` return `Result` without performing payment/DB side effects?
8. Is `display` exhaustive over the `Result` subtypes?
9. Does `isBillable` use type patterns/flow scoping properly?
10. Do monetary calculations avoid `double` and handle overflow?
11. Does `Card` accept only four simulated digits without collecting real card data?
12. Do tests cover null, invalid, promo, normal, overflow, and cancel cases?
13. Does adding a nested `Payment` subtype have its own test so the fallback does not mask bugs?
14. Are outputs deterministic, and do file/class names and Java commands match?
15. Can you explain when to use polymorphism/domain services instead of a pattern switch?

If you cannot answer an item with certainty, try writing an additional test for that exact item. **A green build does not prove business correctness; happy-path-only tests are not enough either**.

## 19. Knowledge Summary

The ShopFlow mini project shows how pattern matching can clarify a multi-variant processing flow without scattered casts:

1. **Sealed hierarchies** model the sets of `Command`, `Shipment`, `Payment`, and `Result`.
2. **Records** create concise domain data and keep components typed.
3. **Nested record patterns** read the exact structure Cart → Customer/Contact → Shipment/Payment.
4. **`when` guards** select rules by quantity, email, and validity conditions.
5. **`switch` expressions** produce a `Result` whose exhaustiveness the compiler can check.
6. **`case null`** defines null selector handling; nested nulls require dedicated guards/fallbacks.
7. **`instanceof` type patterns** allow asking a simple question about `Approved` with flow scoping.
8. **Tests and exact arithmetic** protect monetary values and business decisions.
9. **Compiler feedback** helps catch unhandled subtypes or dominated cases, but does not replace testing nested variants and domain rules.

For real applications, maintain clear boundaries between **model, decision, calculation, execution, and adapter**. Pattern matching is a tool for expressing logic by type/structure; its greatest value comes from using it in the right place with reliable invariants and tests, not merely from shorter syntax.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- Java Language Specification SE 21 — `14.30 Patterns`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 395 — Records: https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
