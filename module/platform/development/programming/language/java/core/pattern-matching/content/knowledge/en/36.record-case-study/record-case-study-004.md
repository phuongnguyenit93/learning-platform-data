# Checking Conditions with `when` in Record Patterns (Java 21)

## 1. The Problem: A Record Matches the Type, Not Necessarily the Conditions

Suppose an order-processing system needs to classify inputs into: **approved**, **awaiting payment**, **underage**, **needs manual review**, **missing data structure**, **null input**, or **unsupported**. The data is passed as nested `record`s: `Purchase` has `Customer` and `Money`.

Type checking alone does not solve the full requirement: a `Purchase` object can still have an unverified `Customer`, a zero amount, an invalid currency code, or be unpaid. Java 21 solves classification by **structure + condition** using a `case` label with a **record pattern** and a **`when` guard**.

Compact example:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when eligible(orderId, id, age, verified,
                      currency, amount, paid) ->
        "APPROVED:" + orderId;
```

Where:

- `Purchase(...)` checks the outer object and binds its components.
- `Customer(...)` and `Money(...)` are **nested record patterns**, requiring the corresponding components to be matching records and not `null`.
- `var orderId`, `var age`, `var amount`, `var paid`, etc. declare **pattern variables**, whose scope is valid inside `when` and the body of that branch.
- `eligible(...)` is a method that checks business rules and returns `boolean`. The guard is only invoked **after** the entire nested record pattern has matched.
- If the pattern matches but `eligible(...) == false`, Java tries the next branch rather than jumping straight to `default`.

**Goals after this lesson:** design `null`-safe guards on your own, preserve priority order, use `BigDecimal` for monetary amounts, write a runnable Java 21 program, test boundary/exception cases, and understand compile-time dominance errors.

**Version requirement:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) became standard features in **Java 21**. With JDK 21+, you can use `javac --release 21`; `--enable-preview` is not needed. The simple `instanceof Type variable` pattern has been standard since Java 16, whereas `when` in a pattern switch is Java 21 syntax.

## 2. Exact Mechanism of the `case Pattern when Expression` Label

A guarded pattern label has the form:

```java
case SomeRecord(var x, var y) when predicate(x, y) -> result;
```

The snippet above is **illustrative syntax** inside a `switch` expression, assuming `SomeRecord` exists and `predicate` returns `boolean`.

When `switch` evaluates a guarded pattern label, the logical sequence is:

1. Check whether the selector can match the pattern of the `case` label.
2. For a record pattern, deconstruct the record via its accessors and continue matching its components/nested patterns. If a nested record pattern does not match, **the guard of that case does not run**.
3. Once the pattern matches, the variables `x` and `y` are bound; Java evaluates the expression after `when`.
4. If the expression returns `true`, the case is selected, the branch body executes, and the switch expression produces its result.
5. If the expression returns `false`, the switch continues searching for another matching label in order; a later branch may have the same record pattern without a guard.
6. If the guard expression **throws an exception**, branch selection terminates abruptly with that exception; Java **does not** treat an exception as `false` to fall through to a fallback.

Distinguish these three states:

| State | Example | Consequence |
| --- | --- | --- |
| Pattern does not match | `Purchase.customer == null` while the label requires `Customer(...)` | Skips the guard, tries the next case |
| Pattern matches, guard is false | `paid == false` while the label requires `eligible(...) == true` | Guard runs, returns `false`, tries the next case |
| Pattern matches, guard throws | `when text.length() > 0` with `text == null` | Throws `NullPointerException`; does not enter the next case |

This is a crucial distinction when testing record patterns: **selecting the right case** is not enough; you must know whether the guard is evaluated and whether it causes side effects or exceptions.

### 2.1. `when` Attaches to a Pattern, Not an Ordinary Constant Label

Standard syntax to remember:

```java
case String s when s.length() >= 3 -> "long enough";
case String s -> "short";
```

Do not use the old preview syntax `case String s && s.length() >= 3` in Java 21 projects. With `instanceof`, do not write `instanceof String s when ...`; use `instanceof String s && ...`.

## 3. Designing the Record Model for the Case Study

The examples use the following records:

```java
record Customer(String id, int age, boolean verified) {}
record Money(String currency, BigDecimal amount) {}
record Purchase(String orderId, Customer customer,
                Money total, boolean paid) {}
```

These declarations require importing `java.math.BigDecimal`. In the complete program in Section 8, the records are placed inside the `RecordWhenCaseStudy` class.

| Record / component | Meaning in this lesson | Notes |
| --- | --- | --- |
| `Customer.id` | Customer ID | Can be `null` or blank; must be checked |
| `Customer.age` | Age | Non-null `int`; 18 is the illustrative threshold |
| `Customer.verified` | Verified flag | `boolean`; not real account verification |
| `Money.currency` | Currency unit | Example only accepts the exact string `"VND"` |
| `Money.amount` | Monetary amount | `BigDecimal` can be `null`; must be positive and within limit |
| `Purchase.orderId` | Order ID | Must be non-blank under the approval condition |
| `Purchase.paid` | Paid flag | If false, classified as awaiting payment by priority |
| `Purchase.customer/total` | Two nested records | Can be `null`; nested record pattern fails in that case |

**Domain boundaries:** This is a case study for learning `when` and pattern matching. It **does not** process payments, grant access, query customer systems, or represent real financial policy. Thresholds and conditions are chosen for clear tests.

### 3.1. Why `BigDecimal` for Money?

If `double` is used for monetary amounts, decimal representations like `0.1` can have binary rounding errors. In the example, `BigDecimal` allows comparing by decimal value using `compareTo(...)`:

```java
private static final BigDecimal LIMIT = new BigDecimal("5000000");

// Only accept amount > 0 and amount <= LIMIT:
amount != null && amount.signum() > 0
        && amount.compareTo(LIMIT) <= 0
```

This is a fragment inside a class that has imported `BigDecimal`. When comparing BigDecimal **values**, `compareTo` is usually more appropriate than `equals` because `BigDecimal("1.0")` and `BigDecimal("1.00")` compare as 0 via `compareTo`, yet are not `equals` due to different scales. However, if scale is part of the contract, the choice of comparison must reflect that requirement.

## 4. Extracting Long Conditions into a Meaningful Predicate

### 4.1. Inline Guards Can Be Hard to Review

You can write:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when orderId != null && !orderId.isBlank()
                && id != null && !id.isBlank()
                && age >= 18 && verified
                && "VND".equals(currency)
                && amount != null && amount.signum() > 0
                && amount.compareTo(LIMIT) <= 0 && paid ->
        "APPROVED:" + orderId;
```

This syntax is valid inside a switch with the appropriate records and helpers. However, a `case` label packed with detailed conditions makes the meaning "**eligible for approval**" hard to see. When those conditions are also unit-tested separately, extract them into a boolean method with a business-meaningful name.

### 4.2. A Safe `eligible(...)` Method

```java
static boolean eligible(String orderId, String id, int age,
                        boolean verified, String currency,
                        BigDecimal amount, boolean paid) {
    return orderId != null && !orderId.isBlank()
            && id != null && !id.isBlank()
            && age >= 18 && verified
            && "VND".equals(currency)
            && amount != null && amount.signum() > 0
            && amount.compareTo(LIMIT) <= 0
            && paid;
}
```

This is a helper inside a class that declares `LIMIT` and imports `BigDecimal`. Each part plays a role:

- Check `orderId != null` **before** calling `isBlank()`.
- Check `id != null` before the corresponding operation.
- The conditions `age >= 18` and `verified` do not depend on nullable references.
- Write `"VND".equals(currency)` to handle `currency == null` safely.
- Check `amount != null` before `signum()`/`compareTo()`.
- `&&` is a **short-circuit** operator: when one operand is false, subsequent operands are not evaluated.
- The method only returns `boolean`; it does not write to a DB or perform unintended business actions.

In the final clause, `paid` is a condition for approval, not a call that executes a payment.

### 4.3. When Should a Helper Accept the Whole Record?

You could also write:

```java
static boolean eligible(Purchase p) {
    return p.orderId() != null && !p.orderId().isBlank()
            && p.customer() != null
            && p.customer().id() != null
            && p.total() != null;
}
```

This is **a compact helper illustrating the signature**, not a replacement for the full `eligible(...)` formula in the main program. Accepting the record is more concise when many components are needed, but it may invoke accessors multiple times and must handle null nested records. Switching from nested record deconstruction to `case Purchase p when eligible(p)` can change the number and order of accessor calls if a record overrides its getters.

In a refactor aimed solely at improving readability, keep the existing pattern structure and move **the exact condition expression** into the helper; do not simultaneously change how deconstruction works and the business logic without equivalent tests.

## 5. Ordering Branches to Match Business Priority

We define the decision order as follows:

1. If all conditions are met, return `APPROVED:<orderId>`.
2. If all nested records are present but `paid == false`, return `AWAIT_PAYMENT`.
3. If not caught by earlier branches and `age < 18`, return `UNDERAGE`.
4. `Purchase` instances with all nested records present that fail other conditions return `MANUAL_REVIEW`.
5. `Purchase` instances missing the `Customer` or `Money` record return `MISSING_DETAILS`.
6. A `null` selector returns `NULL_INPUT`.
7. Any object type other than `Purchase` returns `UNSUPPORTED`.

This is an **intentional priority order for this example**, not a result list inferred automatically by the compiler.

```java
static String decide(Object input) {
    return switch (input) {
        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid)
                when eligible(orderId, id, age, verified,
                              currency, amount, paid) ->
                "APPROVED:" + orderId;

        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid)
                when !paid -> "AWAIT_PAYMENT";

        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid)
                when age < 18 -> "UNDERAGE";

        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid) ->
                "MANUAL_REVIEW";

        case Purchase p -> "MISSING_DETAILS";
        case null -> "NULL_INPUT";
        default -> "UNSUPPORTED";
    };
}
```

**Exact explanation:** If a 17-year-old customer **has not paid**, the first branch evaluates to `false`, the second branch `when !paid` is selected, and the result is **`AWAIT_PAYMENT`**, not `UNDERAGE`. If you want age to take priority over payment status, you must **swap the order of the two guards** and update the tests; that is a business behavior change.

### 5.1. Why Do We Need a Branch with the Same Record Pattern and No Guard?

The branch:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid) ->
        "MANUAL_REVIEW";
```

comes **after** the guarded branches. It acts as the fallback for orders that have all nested records present but fail all specific conditions. If this branch were placed above them, the guarded branches with the same structure below would be **dominated**, and the compiler can reject it.

### 5.2. Pattern Matching Does Not Mean Valid Data

Records allow creating `Customer(null, 20, true)` and `Money(null, null)`. `Customer(var id, ...)` and `Money(var currency, var amount)` can still match a **non-null** record object and bind **null** components. Therefore, `eligible(...)` must take responsibility for validating the values.

Conversely, if `Purchase.customer() == null`, the nested **record pattern** `Customer(...)` does not match and the guard does not run. In that case, the subsequent `case Purchase p` handles it and returns `MISSING_DETAILS`.

## 6. Test Suite Must Distinguish Pattern Failure from Guard Failure

The matrix below is the contract of the example, before looking at the program.

| Representative input | Nested pattern | Guard / priority | Result |
| --- | --- | --- | --- |
| Age 20, verified, VND 5,000,000, paid | Matches | `eligible=true` | `APPROVED:O1` |
| Age 18, VND 100, paid | Matches | Eligible age boundary | `APPROVED:O2` |
| Total 5,000,001 | Matches | Exceeds limit | `MANUAL_REVIEW` |
| Unpaid, age 20 | Matches | `!paid=true` | `AWAIT_PAYMENT` |
| Unpaid, age 17 | Matches | `!paid` precedes age guard | `AWAIT_PAYMENT` |
| Paid, age 17 | Matches | `age<18` | `UNDERAGE` |
| Blank/null ID | Matches | Helper rejects null/blank | `MANUAL_REVIEW` |
| `verified=false` | Matches | Not eligible for approval | `MANUAL_REVIEW` |
| `orderId=null` or blank | Matches | Not eligible for approval | `MANUAL_REVIEW` |
| `currency=null` or `"USD"` | Matches | Not `"VND"` | `MANUAL_REVIEW` |
| `amount=null`, 0, or negative | Matches | Not positive / missing value | `MANUAL_REVIEW` |
| `customer=null` | **Does not match** nested `Customer(...)` | Guard does not run | `MISSING_DETAILS` |
| `total=null` | **Does not match** nested `Money(...)` | Guard does not run | `MISSING_DETAILS` |
| Selector `null` | Does not match `Purchase(...)` | `case null` | `NULL_INPUT` |
| Selector `Integer` | Does not match `Purchase(...)` | `default` | `UNSUPPORTED` |

The two cases `amount=null` and `total=null` are **not the same**:

- `total=null`: there is no `Money` object to deconstruct, so the nested record pattern does not match.
- `new Money("VND",null)`: there is a `Money` record, `var amount` binds `null`, and the helper returns `false`.

The same applies to `customer=null` versus `new Customer(null,20,true)`. This is why tests should not lump every kind of `null` into one generic outcome.

## 7. Guards and `instanceof`: Same Idea, Different Syntax

A structure + condition check can be written using `instanceof` with the `&&` operator:

```java
static boolean matchingAndEligible(Object input) {
    return input instanceof Purchase(
            var orderId,
            Customer(var id, var age, var verified),
            Money(var currency, var amount), var paid)
            && eligible(orderId, id, age, verified,
                        currency, amount, paid);
}
```

In this example:

1. Java tests the nested record pattern on the left-hand side of `&&`.
2. If the pattern does not match, `eligible(...)` **is not called**.
3. If it matches, the pattern variables are bound and in valid scope on the right-hand side, where the helper is called.
4. The resulting expression is a `boolean`; no `switch` is needed when asking only a single true/false question.

**Do not write:**

```java
// INTENTIONALLY WRONG: when is not valid syntax for instanceof.
if (input instanceof Purchase p when eligible(p)) {
    // ...
}
```

This snippet also assumes a method `eligible(Purchase)` that is not defined in the runnable example; the key point is that **after `instanceof` you use `&&`, not `when`**.

### When Should You Choose Which?

- **Only need a true/false check:** `instanceof ... && predicate(...)` is usually more concise.
- **Need multi-way classification and prioritized guards:** `switch` with `case ... when ...` is clearer.
- **Only checking the outer type:** `instanceof Purchase p` or `case Purchase p` is enough; avoid deconstructing every component unnecessarily.
- **Data with custom accessors or side effects:** evaluate accessor cost and invocation order before refactoring from type-only to nested record patterns.

## 8. Complete Java 21 Program: `RecordWhenCaseStudy.java`

The following program **runs standalone on JDK 21**, without Maven/JUnit. It exercises 20 classification cases, two `instanceof` checks, a counter proving when guards run, and one guard case that intentionally throws `NullPointerException` to demonstrate that exceptions do not become `false`.

Create the exact file **`RecordWhenCaseStudy.java`**:

```java
import java.math.BigDecimal;
import java.util.Objects;

public class RecordWhenCaseStudy {
    record Customer(String id, int age, boolean verified) {}
    record Money(String currency, BigDecimal amount) {}
    record Purchase(String orderId, Customer customer,
                    Money total, boolean paid) {}
    record Probe(String text) {}

    static final BigDecimal LIMIT = new BigDecimal("5000000");
    static int tests;
    static int guardProbes;

    static boolean eligible(String orderId, String id, int age,
                            boolean verified, String currency,
                            BigDecimal amount, boolean paid) {
        return orderId != null && !orderId.isBlank()
                && id != null && !id.isBlank()
                && age >= 18 && verified
                && "VND".equals(currency)
                && amount != null && amount.signum() > 0
                && amount.compareTo(LIMIT) <= 0
                && paid;
    }

    static String decide(Object input) {
        return switch (input) {
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when eligible(orderId, id, age, verified,
                                  currency, amount, paid) ->
                    "APPROVED:" + orderId;
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when !paid -> "AWAIT_PAYMENT";
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when age < 18 -> "UNDERAGE";
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid) ->
                    "MANUAL_REVIEW";
            case Purchase p -> "MISSING_DETAILS";
            case null -> "NULL_INPUT";
            default -> "UNSUPPORTED";
        };
    }

    static boolean paidProbe(boolean paid) {
        guardProbes++;
        return paid;
    }

    static String traced(Object input) {
        return switch (input) {
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when paidProbe(paid) -> "PAID";
            case Purchase p -> "OTHER_PURCHASE";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static String inspect(Object input) {
        return switch (input) {
            case Probe(var text) when text.length() > 0 -> "NONEMPTY";
            case Probe p -> "EMPTY";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static boolean matchingAndEligible(Object input) {
        return input instanceof Purchase(
                var orderId, Customer(var id, var age, var verified),
                Money(var currency, var amount), var paid)
                && eligible(orderId, id, age, verified,
                            currency, amount, paid);
    }

    static Purchase purchase(String orderId, String id, int age,
                             boolean verified, String currency,
                             String amount, boolean paid) {
        return new Purchase(
                orderId, new Customer(id, age, verified),
                new Money(currency, amount == null
                        ? null : new BigDecimal(amount)), paid);
    }

    static void check(String name, Object value, String expected) {
        String actual = decide(value);
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(name + ": expected=" + expected
                    + ", got=" + actual);
        }
        tests++;
        System.out.println(name + " => " + actual);
    }

    public static void main(String[] args) {
        check("at-limit",
                purchase("O1","C1",20,true,"VND","5000000",true),
                "APPROVED:O1");
        check("below-limit",
                purchase("O2","C2",18,true,"VND","100",true),
                "APPROVED:O2");
        check("over-limit",
                purchase("O3","C3",20,true,"VND","5000001",true),
                "MANUAL_REVIEW");
        check("unpaid",
                purchase("O4","C4",20,true,"VND","100",false),
                "AWAIT_PAYMENT");
        check("minor-unpaid",
                purchase("O5","C5",17,true,"VND","100",false),
                "AWAIT_PAYMENT");
        check("minor-paid",
                purchase("O6","C6",17,true,"VND","100",true),
                "UNDERAGE");
        check("blank-id",
                purchase("O7"," ",20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("null-id",
                purchase("O8",null,20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("unverified",
                purchase("O9","C9",20,false,"VND","100",true),
                "MANUAL_REVIEW");
        check("null-order-id",
                purchase(null,"C10",20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("blank-order-id",
                purchase(" ","C11",20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("null-currency",
                purchase("O12","C12",20,true,null,"100",true),
                "MANUAL_REVIEW");
        check("other-currency",
                purchase("O13","C13",20,true,"USD","100",true),
                "MANUAL_REVIEW");
        check("null-amount",
                purchase("O14","C14",20,true,"VND",null,true),
                "MANUAL_REVIEW");
        check("zero-amount",
                purchase("O15","C15",20,true,"VND","0",true),
                "MANUAL_REVIEW");
        check("negative-amount",
                purchase("O16","C16",20,true,"VND","-1",true),
                "MANUAL_REVIEW");
        check("null-customer",
                new Purchase("O17",null,new Money("VND",BigDecimal.ONE),true),
                "MISSING_DETAILS");
        check("null-money",
                new Purchase("O18",new Customer("C18",20,true),null,true),
                "MISSING_DETAILS");
        check("null-selector", null, "NULL_INPUT");
        check("other-type", 42, "UNSUPPORTED");
        System.out.println("DECISION CASES PASS: " + tests);

        Purchase approved = purchase(
                "O19","C19",20,true,"VND","15",true);
        if (!matchingAndEligible(approved)
                || matchingAndEligible(
                    new Purchase("O20",null,approved.total(),true))) {
            throw new AssertionError("instanceof guard parity");
        }
        System.out.println("INSTANCEOF CHECKS PASS: 2");

        String noNested = traced(
                new Purchase("O21",null,approved.total(),true));
        String notPaid = traced(
                purchase("O22","C22",20,true,"VND","100",false));
        String isPaid = traced(approved);
        if (!noNested.equals("OTHER_PURCHASE")
                || !notPaid.equals("OTHER_PURCHASE")
                || !isPaid.equals("PAID")
                || guardProbes != 2) {
            throw new AssertionError("guard timing");
        }
        System.out.println("GUARD PROBES PASS: " + guardProbes);

        try {
            inspect(new Probe(null));
            throw new AssertionError("expected NullPointerException");
        } catch (NullPointerException ex) {
            System.out.println("UNSAFE GUARD => NullPointerException");
        }
        System.out.println("ALL CHECKS PASSED");
    }
}
```

### 8.1. Compile and Run

Use JDK 21+:

```bash
javac --release 21 RecordWhenCaseStudy.java
java RecordWhenCaseStudy
```

**Verified exact stdout:**

```text
at-limit => APPROVED:O1
below-limit => APPROVED:O2
over-limit => MANUAL_REVIEW
unpaid => AWAIT_PAYMENT
minor-unpaid => AWAIT_PAYMENT
minor-paid => UNDERAGE
blank-id => MANUAL_REVIEW
null-id => MANUAL_REVIEW
unverified => MANUAL_REVIEW
null-order-id => MANUAL_REVIEW
blank-order-id => MANUAL_REVIEW
null-currency => MANUAL_REVIEW
other-currency => MANUAL_REVIEW
null-amount => MANUAL_REVIEW
zero-amount => MANUAL_REVIEW
negative-amount => MANUAL_REVIEW
null-customer => MISSING_DETAILS
null-money => MISSING_DETAILS
null-selector => NULL_INPUT
other-type => UNSUPPORTED
DECISION CASES PASS: 20
INSTANCEOF CHECKS PASS: 2
GUARD PROBES PASS: 2
UNSAFE GUARD => NullPointerException
ALL CHECKS PASSED
```

The program uses `if (...) throw new AssertionError(...)` checks so that all verifications run even when the JVM is launched without `-ea`. The final message appears **only when** all expected checks complete.

### 8.2. How to Read the Special Results

- **`at-limit`** and **`below-limit`** prove that `amount.compareTo(LIMIT) <= 0` includes the limit itself; an 18-year-old also passes `age >= 18`.
- **`minor-unpaid`** returns `AWAIT_PAYMENT` because the `!paid` guard precedes the `age < 18` guard.
- **`null-id`, `null-amount`** are handled in the `MANUAL_REVIEW` branch, because the nested records still match and the helper handles null components safely.
- **`null-customer` and `null-money`** return `MISSING_DETAILS` because the nested record pattern does not match.
- **`INSTANCEOF CHECKS PASS: 2`** proves that pattern + `&& eligible(...)` works on one valid input and one input missing a nested customer; it does not conflate `when` syntax with `instanceof`.
- **`GUARD PROBES PASS: 2`** is the key point: `traced(...)` is called three times, yet `paidProbe(...)` runs only twice. The `Customer==null` case never reaches the guard, whereas the two `Purchase` instances with nested records do run the guard, even when the result is `false`.
- **`UNSAFE GUARD => NullPointerException`** is an intentional verification of `Probe(var text)` with `text==null`. The guard throws an exception; Java does not automatically convert the exception to `false`.

The program does not measure performance, connect to external services, or perform any real payments.

## 9. Understanding `null`, Guards, and Short-Circuiting in Depth

### 9.1. Three Distinct Levels of `null`

Consider the expression:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when eligible(orderId, id, age, verified,
                      currency, amount, paid) ->
        "APPROVED:" + orderId;
```

Three `null` categories must be distinguished:

1. **Null selector:** `input == null` → dedicated `case null`; `default` does not handle `null` by default.
2. **Null intermediate record:** `customer == null` or `total == null` → nested `Customer(...)` or `Money(...)` does not match; the guard is skipped.
3. **Null component reference:** `id == null` or `amount == null` when the intermediate record is non-null → `var` can bind `null`; the guard **runs** and must check safely.

Do not use a single `input==null` test to represent all three categories.

### 9.2. A Nested Type Pattern Does Not Always Mean Non-Null

In Java 21, a **nested type pattern** on a record component can be *null-matching* when it is unconditional with respect to the component's declared type. For example, the record `Money(String currency, BigDecimal amount)` can match the pattern `Money(String currency, BigDecimal amount)` and bind a null component under appropriate unconditional conditions. The `var` patterns used in the main program also allow binding null component references.

**Rule to remember:** A record pattern such as `Money(...)` does not match a **null Money object**, but each **component** pattern is not an automatic non-null validation mechanism. If business rules require non-null, you must place the corresponding check in the guard/helper.

### 9.3. Why Must `&&` Conditions Keep Their Order?

```java
return id != null && !id.isBlank()
        && amount != null && amount.signum() > 0;
```

This is safe short-circuiting. Reversing it to:

```java
// INTENTIONALLY UNSAFE:
return !id.isBlank() && id != null;
```

will throw an NPE when `id==null`. These fragments are in the context of a boolean-returning method. Even when moving a long guard into a helper, you must preserve the order if there are null checks or side effects.

### 9.4. Why Can `when text.length() > 0` Throw an Error?

The full program has:

```java
record Probe(String text) {}

static String inspect(Object input) {
    return switch (input) {
        case Probe(var text) when text.length() > 0 -> "NONEMPTY";
        case Probe p -> "EMPTY";
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

When `input = new Probe(null)`, the outer record pattern matches, `var text` binds `null`, and `text.length()` causes a `NullPointerException`. **The branch `case Probe p -> "EMPTY"` is not tried** when the guard throws an exception; it is only tried when the guard finishes evaluating and returns `false`.

**Fix if you want a safe false:**

```java
case Probe(var text)
        when text != null && !text.isEmpty() -> "NONEMPTY";
case Probe p -> "EMPTY";
```

This is a policy change from throwing an NPE to falling back to `EMPTY` for `Probe(null)`, so it should be treated as a separate business/test decision, not automatically as a behavior-preserving refactor.

## 10. Evaluating Guards at the Right Time and Avoiding Hidden Side Effects

Although Java allows calling methods with side effects inside a guard, an ideal predicate should be **pure**: take inputs and return `boolean`, without sending HTTP requests, writing to a DB, charging money, writing business logs, or mutating state.

In the program, `eligible(...)` is a pure helper. The `paidProbe(...)` method is a **test-only measurement probe**:

```java
static int guardProbes;

static boolean paidProbe(boolean paid) {
    guardProbes++;
    return paid;
}
```

The counter lets us observe the exact number of guard evaluations in a single-threaded fixture. Do not put mutable state like this into production code to "count every guard" without proper instrumentation and thread-safety design.

### 10.1. Guards Run Only After Nested Patterns Match

Example:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when paidProbe(paid) -> "PAID";
```

If `Purchase.customer() == null`, the `Customer(...)` record pattern fails; `paidProbe` **is not called**. If both customer and money are valid, the guard is called to return true/false.

### 10.2. Argument Evaluation Order Still Matters

Java evaluates method call arguments **before** invoking the helper. A risky refactor is moving an expensive or side-effecting expression from the right-hand side of `&&` into an eagerly evaluated argument.

```java
// Before: slowCheck() only runs if id is non-null.
boolean before = id != null && slowCheck();

// After: slowCheck() is always evaluated before isValid(...).
boolean after = isValid(id, slowCheck());
```

This snippet illustrates argument evaluation semantics; `slowCheck` and `isValid` are hypothetical helpers, **not standalone runnable code**. If `slowCheck` can throw or has side effects, the two versions can behave differently.

Prefer passing bound components into the helper and performing the entire `&&` chain in the verified order inside the helper.

## 11. Dominance and `when true` / `when false`

The Java 21 compiler checks whether any case is **dominated by a preceding case**. Basic rules:

- An unguarded pattern placed before a narrower pattern can make the later branch unreachable.
- A case with a normal `when` guard **is not automatically considered to cover** all values of the same pattern, because the compiler does not solve arbitrary boolean expressions.
- `when true` is a special case: a constant `true` guard is treated like an **unguarded label** for dominance purposes.
- `when false`, if it is a **constant expression** with value `false`, is rejected by Java 21 at compile time.
- A guard must have type `boolean` or `Boolean` in a valid context; `String` cannot be used directly as a condition.

The **intentionally non-compiling** examples below use the record:

```java
record Order(String id, int quantity) {}
```

### 11.1. Broad Branch Before Specific Guard — Dominance

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Order order -> "all";
    case Order(var id, var quantity) when quantity > 0 -> "positive";
    default -> "other";
};
```

The compiler reports `this case label is dominated by a preceding case label`. Fix it by placing the guarded branch first and the unguarded branch after.

### 11.2. Constant `true` Guard Can Still Dominate

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Order order when true -> "all";
    case Order other -> "duplicate";
    default -> "other";
};
```

Despite the `when` keyword, the `true` guard causes the first branch to be treated as unguarded, shadowing the next branch. This is **compiler-verified Java 21 behavior**.

### 11.3. Constant `false` Guard Is Rejected

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Order order when false -> "never";
    case Order other -> "other";
    default -> "not order";
};
```

The compiler reports the equivalent of `this case label has a guard that is a constant expression with value 'false'`. If you need to disable a branch via configuration, do not write `when false` directly; either remove the branch or use intentional, tested configuration logic.

### 11.4. Non-Boolean Guard

```java
// INTENTIONALLY WRONG if Order.id() returns String:
return switch (value) {
    case Order order when order.id() -> "bad";
    default -> "other";
};
```

The compiler reports `String cannot be converted to boolean`. To check that the ID is non-empty, use an explicit boolean condition:

```java
case Order order
        when order.id() != null && !order.id().isBlank() -> "valid";
```

### 11.5. When Two Guards Can Both Be True

Suppose a transaction has `age==17` and `paid==false`. Both expressions `when !paid` and `when age < 18` are true. The compiler does not report dominance by default for these two guards; **the earlier branch wins**. Do not write tests only for cases where each guard is true independently and omit cases where **both are true simultaneously**.

## 12. Scope and Usage of Pattern Variables

In:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when eligible(orderId, id, age, verified,
                      currency, amount, paid) ->
        "APPROVED:" + orderId;
```

the pattern variables `orderId`, `id`, `age`, `verified`, `currency`, `amount`, `paid` are in scope within the `when` expression and the body of the selected case, following flow-scoping rules.

**Do not use a pattern variable from an earlier case in another case.** Example:

```java
// INTENTIONALLY WRONG: id from the first case does not exist in default.
return switch (input) {
    case Customer(var id, var age, var verified) -> id;
    default -> id;
};
```

Across different cases, you can declare **the same variable names** in independent patterns according to scoping rules; for example, in the main program, `orderId` and `id` are bound repeatedly in multiple cases and compile cleanly.

In `instanceof` with `&&`, the right-hand side may use the bound pattern variables if the left-hand side matches successfully:

```java
if (input instanceof Customer(var id, var age, var verified)
        && id != null && age >= 18) {
    System.out.println(id);
}
```

On the other hand, using a variable from a failed match across `||` or outside a scope where the compiler can prove it is definitely matched will cause an error. When the IDE reports that a variable cannot be resolved, inspect the flow path before reaching for a manual cast.

## 13. Regression Test Suite for Record Guards

For this case study, tests should be clearly separated into three layers:

1. **Structure testing:** Do `Purchase` and nested `Customer`/`Money` match? How does a null component differ from a null record?
2. **Predicate testing:** What values does `eligible(...)` accept/reject? Is there any NPE from missing short-circuiting?
3. **Branch/priority testing:** When two guards are both true, which case is selected? Does a false guard fall through to the right fallback?

The program in Section 8 covers:

- 20 decision cases with explicit expected strings.
- Two `instanceof + &&` cases verifying both match success and failure paths.
- Three calls to `traced`, with exactly two guard evaluations.
- One guard case intentionally throwing `NullPointerException` to verify exceptions are not used as fallbacks.
- Boundary cases: age **17/18**, amount **0**, amount **5,000,000/5,000,001**, blank/null IDs, null nested records, `paid` false.

### 13.1. JUnit 5: Turning the Table into Parameterized Tests

In a project with JUnit Jupiter and the `junit-jupiter-params` dependency, tests can be organized as a table. The snippet below is a **JUnit code fragment**; it does not run standalone on the JDK alone and does not replace the main Java file in Section 8:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import java.util.stream.Stream;

class RecordWhenCaseStudyTest {
    static Stream<Arguments> scenarios() {
        return Stream.of(
            Arguments.of("eligible",
                RecordWhenCaseStudy.purchase(
                    "O1","C1",18,true,"VND","5000000",true),
                "APPROVED:O1"),
            Arguments.of("unpaid minor",
                RecordWhenCaseStudy.purchase(
                    "O2","C2",17,true,"VND","100",false),
                "AWAIT_PAYMENT"),
            Arguments.of("missing amount",
                RecordWhenCaseStudy.purchase(
                    "O3","C3",20,true,"VND",null,true),
                "MANUAL_REVIEW"),
            Arguments.of("null selector", null, "NULL_INPUT")
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("scenarios")
    void decidesAsSpecified(String description, Object input,
                            String expected) {
        assertEquals(expected, RecordWhenCaseStudy.decide(input));
    }
}
```

**Usage context:** place the test in the same package as `RecordWhenCaseStudy` (since the example records/helpers have package-private access) or redesign an appropriate public API; configure the JUnit Jupiter test runner in Maven/Gradle. When using standalone JUnit, do not rely on `System.out.println` to verify passes — use the test framework's assertions.

### 13.2. Property-Based Checks Instead of Single Inputs

Rules that can be verified across many generated values:

- With all nested records present and `paid=false`, no `Purchase` is approved; in this lesson's order, `AWAIT_PAYMENT` takes priority over `UNDERAGE`.
- With `amount <= 0` and `paid=true`, a customer of legal age with complete details falls into `MANUAL_REVIEW`.
- Replacing a non-null `Customer` with `null` causes the nested pattern to fail, shifting the result from a specific record branch to `MISSING_DETAILS`.
- With different order IDs under otherwise valid conditions, the output `APPROVED:<orderId>` must reflect the exact bound `orderId`.
- When `amount == LIMIT`, the result can still be `APPROVED`; `amount > LIMIT` cannot be approved.

When using property-based testing, generate data **within the test domain**, keep a reproducible seed, and add minimal regression cases when bugs are found. Do not write a property asserting "no object ever throws an exception" if the contract allows exceptions for unsafe guards or invalid data.

## 14. Performance, Readability, and Guard Design Quality

`when` is a conditional dispatch mechanism, not a free optimization. If a guard invokes regexes, DB queries, or external calls, its cost can far exceed checking record types. Keeping guards **short, deterministic, clearly named after business domain rules, and pure** helps:

- Reduce confusion when reviewing many cases.
- Unit-test predicates independently.
- Avoid duplicating conditions in multiple places.
- Make `null` handling and `&&` ordering easy to audit.
- Limit unexpected side effects when Java tests one case and moves on to the next.

**However, do not over-extract.** A short guard like `when age < 18` is already clear; creating a helper `isAgeLessThan18(age)` just to hide a single comparison can make code harder to follow.

### 14.1. When Should You Avoid Deep Nested Deconstruction?

If you only need to know `input instanceof Purchase` to log an audit entry by type, `case Purchase p` is usually enough. A pattern like `Purchase(...Customer(...),Money(...))` also extracts components via accessors; on records with custom accessors, this could trigger side effects or exceptions. Choose pattern depth based on the data you **actually need**.

### 14.2. Do Not Blindly Convert `if/else` to `switch` While Ignoring `null`

`if (value instanceof Purchase p)` returns `false` when `value` is null. A `switch` on a null selector without `case null` normally throws an NPE. When refactoring, define the `null` contract upfront and write tests; do not assume `default` is equivalent to the `else` branch of an `if`.

## 15. Common Mistakes and How to Fix Them

### Mistake 1 — Using old preview syntax

`case String s && condition(s)` is syntax from pre-Java 21 previews. In standard Java 21, use `case String s when condition(s)`.

### Mistake 2 — Assuming the guard handles missing nested records

`when condition(...)` **does not run** when nested `Customer(...)` or `Money(...)` fails to match. To classify missing records, include a `case Purchase p` fallback or an appropriate structure.

### Mistake 3 — Assuming record fields are non-null by default

Records do not automatically validate component values. With `Money("VND",null)`, `var amount` still binds `null`, and the helper must avoid dereferencing before checking.

### Mistake 4 — Putting an unguarded branch first

A `case Purchase p` before `Purchase(...) when ...` cases can dominate them. Specific/guarded branches go first; general branches go after.

### Mistake 5 — Assuming the compiler understands all guards

The compiler does not arbitrarily determine whether two complex predicates overlap. If both guards evaluate to true, **the branch that appears first** is chosen. Write tests for overlapping cases.

### Mistake 6 — Constant `false` guard

`when false` with a constant `false` expression is rejected by Java 21. Do not use it to "comment out" a case.

### Mistake 7 — Guard not returning a boolean

If a helper returns `String`, `List`, or a `Predicate<T>` object without calling `.test(...)`, `when` does not have a valid boolean value.

### Mistake 8 — Changing short-circuit order

Moving `amount.signum() > 0` ahead of `amount != null` increases the risk of NPEs. Keep null checks first and test with null components.

### Mistake 9 — Assuming a throwing guard moves to the next case

The runtime does not treat an exception as a `false` guard; it propagates the exception. If you want a safe fallback, the predicate must handle the error condition according to the contract.

### Mistake 10 — Using `BigDecimal.equals` when you want value comparison

For monetary amounts, `compareTo` reflects decimal value comparison even across different scales; `equals` can return different results when scales differ. Choose according to the data contract.

### Mistake 11 — Testing only the predicate in isolation

The predicate may be correct while `switch` picks the wrong branch due to case ordering or null nested records. Test `eligible(...)`, `decide(...)`, and overlapping guard cases together.

### Mistake 12 — Putting too many actions inside `when`

A guard that calls services and mutates state before returning a boolean makes falling through branches unpredictable. Separate boolean decisions from side-effecting actions for easier testing and rollback.

## 16. Code Review Checklist and Definition of Done

- [ ] Project builds on **Java 21** with standard pattern `switch`/record patterns.
- [ ] Outer and nested records accurately model the real data.
- [ ] Predicate names express **rules** (e.g., `eligible`), not hidden actions.
- [ ] Pattern variables are used in `when` within valid flow scope.
- [ ] All nullable component references are checked before dereferencing.
- [ ] Selector `null`, nested record `null`, and component `null` are clearly distinguished.
- [ ] When a nested pattern fails, an appropriate fallback exists and the guard is not called.
- [ ] True/false guard outcomes have clear paths and expected outputs.
- [ ] Guard order reflects the exact priority when multiple conditions are true simultaneously.
- [ ] Unguarded branches follow specific branches; no dominance errors exist.
- [ ] No constant `when false`; no mistyped guards.
- [ ] No preview syntax `case Pattern && condition` in Java 21 code.
- [ ] Guards handle `null` safely and avoid unwanted side effects/exceptions.
- [ ] For `BigDecimal`, values and thresholds are compared using the appropriate API.
- [ ] Tests cover exact age and limit boundaries, paid/unpaid, verified, and null/blank values.
- [ ] Pattern + `instanceof &&` is tested if used in the application.
- [ ] Throwing guard behavior is tested if the contract requires an exception.
- [ ] Compiler gate catches dominance, invalid constant guards, and type errors.
- [ ] Unit tests and CI run on the target JDK/source level.

**Definition of Done:** A reader can explain why each order enters its branch; guards run only when patterns match; null data does not cause unexpected NPEs in the main processing path; and boundary/priority tests have exact expectations. Any change to case ordering or business conditions must be announced as a behavior change and accompanied by updated regression tests.

## 17. Self-Check Questions

**1. Is `when` evaluated before or after a nested record pattern?**  
After. Java only invokes the guard once the pattern in the `case` label has matched.

**2. Does a `Purchase` with `Customer=null` run `eligible(...)` in the nested branch?**  
No, because `Customer(...)` does not match a null object.

**3. Can `Customer(null,20,true)` match `Customer(var id,var age,var verified)`?**  
Yes; `var id` can bind `null`. The guard/helper must check it.

**4. If the first guard returns false, where does Java go?**  
Java continues evaluating the next matching `case` label. If a guard throws an exception, there is no automatic fallback.

**5. What does an unpaid, 17-year-old order return in the example?**  
`AWAIT_PAYMENT`, because the `when !paid` branch is evaluated before `when age < 18`.

**6. Why should you write `"VND".equals(currency)`?**  
Because it handles a null `currency` safely, avoiding calling a method on a null reference.

**7. Should `BigDecimal` limits be compared with `compareTo` or `==`?**  
`compareTo` when comparing numeric values; `==` only compares object identity.

**8. What is special about `when true` and `when false`?**  
Constant `true` is treated as an unguarded pattern for dominance; constant `false` is rejected at compile time.

**9. Can you use `when` after `instanceof Purchase p`?**  
No. Use the `&&` operator to combine a boolean condition.

**10. Why must `case Purchase p` come after `Purchase(...) when ...` branches?**  
Because a broad unguarded branch can dominate specific branches of the same type.

**11. When two guards are both true, which one is selected?**  
The branch that appears first in `switch` order.

**12. What does `GUARD PROBES PASS: 2` prove?**  
Across three calls to `traced`, the guard was evaluated only on the two inputs that had all nested records present.

**13. Is `when amount.signum() > 0` safe if `amount` can be null?**  
No. You need `amount != null && amount.signum() > 0`.

**14. Does `ALL CHECKS PASSED` prove that all production orders are valid?**  
No. It only proves the tested cases against the example's contract. Production still requires its own rules, data, concurrency, and integration tests.

## References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java SE 21 — Pattern Matching for switch: When Clauses](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §14.11 — switch statements, guards and dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS SE 21 §14.30 — Patterns and pattern matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS SE 21 §6.3 — Scope of declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Java SE 21 API — BigDecimal.compareTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html#compareTo(java.math.BigDecimal))
