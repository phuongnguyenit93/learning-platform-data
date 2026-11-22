# Clear Naming, Indentation, and Avoiding Magic Numbers in Java

Readable code helps others understand **meaning and intent** without having to guess from the implementation. In Java 17+, three habits have an immediate impact: naming things to show their role, formatting blocks consistently, and replacing numbers that encode business rules with meaningful names.

## 1. Naming things to state data and actions clearly

| Element | Common Java convention | Example |
| --- | --- | --- |
| Class, interface, enum | `UpperCamelCase`, usually a noun/role | `TicketPricing`, `PaymentService` |
| Method | `lowerCamelCase`, usually starting with a verb | `calculateTicketPriceVnd()`, `sendNotification()` |
| Variable, parameter | `lowerCamelCase`, named for meaning and scope | `customerAge`, `orderTotalVnd` |
| `static final` constant | `UPPER_SNAKE_CASE` | `MINIMUM_ADULT_AGE`, `MAX_RETRY_COUNT` |
| Package name | Lowercase, hierarchical by functional domain | `com.example.tickets` |
| `boolean` variable | Name that reads like a true/false question | `isChild`, `hasPermission`, `canRetry` |

Naming principles:

- **Express purpose:** `customerAge` is clearer than `a`; `calculateTicketPriceVnd` is clearer than `calc()`. Avoid `data`, `result`, `temp`, `value` when you can state specifically what they hold.
- **Include units if easily confused:** `timeoutMillis`, `priceVnd`, `fileSizeBytes`. A name like `timeout` does not tell whether it is milliseconds or seconds.
- **Distinguish close concepts:** `totalPriceVnd` and `discountAmountVnd` differ from `discountPercent`; an amount of money is different from a percentage.
- **Match the scope:** a very short loop variable can be `i` if obvious, but meaningful names are needed for business variables or variables that live across multiple steps.
- **Keep vocabulary consistent:** pick one term, such as `customer`, and use it consistently rather than alternating between `client`, `buyer`, and `user` for the same concept.
- **Do not overuse abbreviations:** `numberOfItems` is easier to understand than `nItm`. Avoid easily confused characters like `l` (lowercase L), `I` (uppercase i), or `O` (uppercase o) on their own.
- **Valid names can still be hard to read:** Java allows many Unicode characters in identifiers, but source code is usually easier to collaborate on with English names, ASCII characters, and consistent conventions. Never use Java keywords as variable names.

Names should reflect actual behavior. For example, a function that validates and then writes data should not be called `validate()` if it also causes side effects. When an API is used in many places, renaming should be done using your IDE's **Rename/Refactor** tool to update all references.

## 2. Indentation and braces make control flow clear

A standard style for Java:

1. Indent **4 spaces per block level**; configure a consistent formatter in the project and do not mix tabs and spaces.
2. Always use `{` and `}` for the body of `if`, `else`, and loops, even when the body has only one statement; place the opening brace after the condition, and align the closing brace with the control structure.
3. Put spaces around operators and after commas; group methods and variables consistently; break overly long expressions at sensible positions.
4. Indent according to **syntactic structure**, not by aligning arbitrarily with spaces just to look pretty. Run a formatter tool before submitting code for review.

The following example is **just a snippet inside a method** and is prone to bugs:

```java
if (isMember)
    discountPercent = 10;
    System.out.println("Đã áp dụng giảm giá");
```

The `println` statement **always executes**, even when `isMember` is `false`: Java determines an `if` body by braces or exactly one statement, not by indentation. Fix it with an explicit block:

```java
if (isMember) {
    discountPercent = 10;
    System.out.println("Đã áp dụng giảm giá");
}
```

Good indentation helps you read the flow, but curly braces define the actual block boundaries. Similarly, keep `else` next to its corresponding `if` block to avoid misreading nested branches. Do not rely on a formatter alone to fix control-flow errors: review the program structure itself.

## 3. Avoiding "magic numbers" (unexplained numbers)

A **magic number** is a number written directly in an expression when the reader cannot tell its meaning or why it was chosen:

```java
int age = 10;
int price = 200000;
if (age < 12) {
    price = price * 75 / 100;
}
```

Reading this snippet alone, it is unclear what age threshold `12` represents, what unit `200000` is in, or whether `75` is a price level or a discount. Such rules are easily missed in one of several places during updates.

How to improve it depends on the **nature** of the value:

| Case | Recommended expression |
| --- | --- |
| Thresholds, limits, fees, or business rates fixed in a code version | `private static final` constants with policy-explaining names, e.g., `MAX_RETRY_COUNT` |
| Time durations | `Duration.ofSeconds(5)`, `Duration.ofMinutes(2)` instead of unitless milliseconds |
| Configuration values that vary by environment or operations | Move into named, validated configuration rather than hardcoding in source |
| Sets of meaningful status values | `enum` or dedicated types instead of cryptic numbers `0`, `1`, `2` |
| Numbers with clear mathematical meaning or basic indices | `0`, `1` can remain literals if the context is truly obvious |

You do not need a constant for *every* number. Name a number only when it states a rule, clarifies units, avoids duplication, or centralizes a point of change. Naming something `NUMBER_12` improves nothing: **the name must explain the meaning, not repeat the value**. A `static final` constant is only immutable in its reference or primitive field value; a mutable object it points to can still change.

## 4. Standalone Java 17+ program

Save with the exact filename **`TicketPricing.java`** (with no `package` declaration) containing the following:

```java
public final class TicketPricing {
    private static final int MINIMUM_ADULT_AGE = 12;
    private static final int STANDARD_TICKET_PRICE_VND = 200_000;
    private static final int CHILD_DISCOUNT_PERCENT = 25;
    private static final int PERCENT_BASE = 100;

    private TicketPricing() {
    }

    public static void main(String[] args) {
        int youngerCustomerAge = 10;
        int adultCustomerAge = 12;

        System.out.println(
                "Khách " + youngerCustomerAge + " tuổi: "
                        + calculateTicketPriceVnd(youngerCustomerAge) + " VND");
        System.out.println(
                "Khách " + adultCustomerAge + " tuổi: "
                        + calculateTicketPriceVnd(adultCustomerAge) + " VND");
    }

    private static int calculateTicketPriceVnd(int customerAge) {
        if (customerAge < 0) {
            throw new IllegalArgumentException("Tuổi phải không âm");
        }

        boolean isChild = customerAge < MINIMUM_ADULT_AGE;
        if (isChild) {
            return STANDARD_TICKET_PRICE_VND
                    * (PERCENT_BASE - CHILD_DISCOUNT_PERCENT)
                    / PERCENT_BASE;
        }

        return STANDARD_TICKET_PRICE_VND;
    }
}
```

Run in the directory containing the file using JDK 17 or later (PowerShell, CMD, macOS, or Linux):

```bash
javac -encoding UTF-8 TicketPricing.java
java TicketPricing
```

**Expected output on stdout:**

```text
Khách 10 tuổi: 150000 VND
Khách 12 tuổi: 200000 VND
```

Explanation: `MINIMUM_ADULT_AGE` clarifies the policy that **under age 12** receives a 25% discount; a customer who is exactly 12 pays the standard price. `STANDARD_TICKET_PRICE_VND` clarifies the unit, `PERCENT_BASE` clarifies the percentage arithmetic, and `calculateTicketPriceVnd` makes the return value clear. The `_` in the numeric literal `200_000` is just for readability; the value is still the integer `200000`. The example uses integer VND and a divisible discount rate so no rounding issue arises; monetary business rules with fractional parts typically need `BigDecimal` or smallest-unit integers along with explicit rounding rules.

## 5. Applying this when editing existing code

1. **Understand the meaning before renaming:** identify what data a variable represents, its unit, and its lifetime; choose a name that matches actual behavior.
2. **Name the rules:** replace cryptic thresholds and rates with named constants or configuration; avoid duplicating the same policy value in multiple places.
3. **Standardize control blocks:** add braces where needed, review `if/else` and loops, then apply a consistent formatter.
4. **Verify behavior after editing:** compile and test at the threshold, just below it, and just above it; in the example above, test ages `11`, `12`, `13` and a negative age. Simple renaming or reformatting must not alter logic.
5. **Keep changes easy to review:** modifying a public API can affect callers, reflection, JSON field names, or external configuration bindings; review those before renaming.

**Self-check:** Can a reader understand each name out of context? Are the units clear? Are there any numbers hiding a policy that needs explanation? Do braces and indentation on branches accurately reflect execution conditions? If two people edit the same file, will the formatter avoid unnecessary diffs? Those are practical signs of maintainable Java code.