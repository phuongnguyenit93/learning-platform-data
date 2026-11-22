# Practice: Billing Program with Conditionals and Loops (Java 17+)

## 1. Problem statement and goal

Build a console Java program to **calculate the bill for a multi-item shopping cart**. The user repeatedly enters a **unit price** and a **quantity**. The program adds each line item's total to a running subtotal, prompts for the next item, and stops when the user enters a **unit price of `0`**. Finally, it uses conditionals to compute the discount and final amount due.

This practice exercise brings together core Java fundamentals: variables and data types, arithmetic operators, `if / else if / else`, `while` loops, `break`, `Scanner`, input validation, methods, and `System.out.println()`.

**Specific rules of the sample program:**

- Unit price is an **integer in VND**. Enter `0` to finish; otherwise it must be between **1 and 1,000,000 VND**.
- Quantity for each item is an integer from **1 to 100**.
- A maximum of **100 line items** is allowed per invoice. One line item can represent multiple identical products via quantity.
- Line total = unit price × quantity. Subtotal = sum of all line totals.
- If subtotal is **500,000 VND or more**, apply a **10%** discount; if **from 200,000 VND to under 500,000 VND**, apply a **5%** discount; below 200,000 VND, **no discount**.
- Discount amount = `subtotal * discountPercent / 100` using integer arithmetic, meaning **whole VND (truncated)**. Total due = subtotal − discount amount.
- Invalid data, unexpected end of input, or exceeding the line-item limit triggers an error message and **does not print a complete invoice**.

The thresholds, limits, and rounding rule above are **assumed practice requirements**, not universal retail rules. In a real project, agree upfront on tax calculation, shipping fees, promo codes, rounding, and cancellation policies.

## 2. Input – Process – Output analysis

| Component | Data or task | Suggested Java type |
| --- | --- | --- |
| **Input** | Unit price per line; `0` is the sentinel to finish | `long` |
| **Input** | Quantity corresponding to each line | `long` or `int` |
| **Process** | Validate price, quantity, line-item count | `if` and comparison operators |
| **Process** | Compute `lineTotal = unitPrice * quantity` | `long` |
| **Process** | Accumulate `subtotal += lineTotal` | `long` |
| **Process** | Choose discount rate 0%, 5%, or 10% | `if / else if / else` |
| **Process** | Compute `discount` and `total` | `long` |
| **Output** | Each line total, subtotal, discount, and total due | `println` |

Use `long` for integer VND amounts to avoid binary floating-point inaccuracy from `double` and to get a larger range than `int`. Within this exercise's bounds, the maximum invoice is `100 × 1_000_000 × 100 = 10_000_000_000` VND, which exceeds `int` range yet fits safely in `long`.

Because the maximum discount rate is 10%, `subtotal * discountPercent` also cannot overflow `long` under these limits. If you remove limits or process massive transactions, add overflow checks or use an appropriate monetary model.

## 3. Algorithm before writing Java

```text
subtotal = 0
itemCount = 0

LOOP:
    Read unitPrice
    IF unitPrice == 0:
        EXIT loop
    IF unitPrice not in [1, 1_000_000]:
        REPORT ERROR and stop program
    IF already at 100 line items:
        REPORT ERROR and stop program

    Read quantity
    IF quantity not in [1, 100]:
        REPORT ERROR and stop program

    lineTotal = unitPrice * quantity
    subtotal = subtotal + lineTotal
    itemCount = itemCount + 1
    Print this line's total

IF subtotal >= 500_000:
    discountPercent = 10
ELSE IF subtotal >= 200_000:
    discountPercent = 5
ELSE:
    discountPercent = 0

discount = subtotal * discountPercent / 100
total = subtotal - discount

Print itemCount, subtotal, discountPercent, discount, and total
```

Here, `while (true)` is a sensible choice because the number of items is not known ahead of time. **`break` runs only when unit price is 0**. Invalid input cases must not be interpreted as a request to finish shopping; they are handled with specific error messages.

Loop invariant after each valid iteration: `itemCount` equals the number of lines entered successfully, and `subtotal` equals the sum of `unitPrice * quantity` across those exact lines. This gives you a basis to double-check accumulation logic.

## 4. Complete program: InvoiceApp.java

Save the full program below in **`InvoiceApp.java`**:

```java
import java.util.Scanner;

public class InvoiceApp {
    private static final long MAX_UNIT_PRICE = 1_000_000L;
    private static final long MAX_QUANTITY = 100L;
    private static final int MAX_LINE_ITEMS = 100;

    private static long readLong(Scanner scanner, String prompt) {
        System.out.println(prompt);

        if (!scanner.hasNextLine()) {
            throw new IllegalArgumentException("missing input");
        }

        String input = scanner.nextLine().strip();
        try {
            return Long.parseLong(input);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("expected an integer", ex);
        }
    }

    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            try {
                long subtotal = 0L;
                int itemCount = 0;

                while (true) {
                    long unitPrice = readLong(
                            scanner, "Unit price VND (0 to finish):");

                    if (unitPrice == 0L) {
                        break;
                    }
                    if (unitPrice < 0L || unitPrice > MAX_UNIT_PRICE) {
                        throw new IllegalArgumentException(
                                "unit price must be from 1 to 1000000");
                    }
                    if (itemCount >= MAX_LINE_ITEMS) {
                        throw new IllegalArgumentException(
                                "too many line items");
                    }

                    long quantity = readLong(scanner, "Quantity:");
                    if (quantity < 1L || quantity > MAX_QUANTITY) {
                        throw new IllegalArgumentException(
                                "quantity must be from 1 to 100");
                    }

                    long lineTotal = unitPrice * quantity;
                    subtotal += lineTotal;
                    itemCount++;

                    System.out.println("Item " + itemCount
                            + ": " + lineTotal + " VND");
                }

                int discountPercent;
                if (subtotal >= 500_000L) {
                    discountPercent = 10;
                } else if (subtotal >= 200_000L) {
                    discountPercent = 5;
                } else {
                    discountPercent = 0;
                }

                long discount = subtotal * discountPercent / 100L;
                long total = subtotal - discount;

                System.out.println("Items: " + itemCount);
                System.out.println("Subtotal: " + subtotal + " VND");
                System.out.println("Discount: " + discountPercent
                        + "% = " + discount + " VND");
                System.out.println("Total: " + total + " VND");
            } catch (IllegalArgumentException ex) {
                System.out.println("Error: " + ex.getMessage());
            }
        }
    }
}
```

### Role of each block

**`readLong(...)` — reading and format checking.** The method prints a prompt, reads an **entire line** with `nextLine()`, trims leading/trailing whitespace with `strip()`, and parses it via `Long.parseLong`. Reading whole lines avoids the classic bug where `nextLine()` consumes the leftover newline after `nextInt()`. On EOF, it reports `missing input`; if it cannot parse an integer, it reports `expected an integer`.

**`while (true)` — iterating over items.** Since the iteration count is unknown upfront, the program continues until it sees price `0`. The `break` statement exits the **innermost enclosing loop** and continues to the discount calculation block right after. Do not confuse `break` with `return`: returning from `main` would skip the summary output.

**`if` — validating each input.** Unit price and quantity have independent bounds. Negative or oversized prices, and zero or oversized quantities, are excluded from the invoice. Price `0` is checked **before** the range check so it serves as the exit sentinel.

**Accumulation — preserving state.** Compute each line's total, add it to `subtotal`, and increment `itemCount` once per valid line. Avoid declaring `subtotal = 0` **inside** the loop, which would reset the total on every iteration.

**`if / else if / else` — selecting exactly one discount tier.** The highest threshold is checked first (`>= 500_000`), followed by `>= 200_000`, and finally 0%. Using two independent `if` statements and applying discounts twice would miscalculate orders at 500,000 VND or above.

**`long` type — integer VND amounts.** The program omits thousand separators so stdout stays consistent across environments. You can use `printf` with an appropriate `Locale` if formatted separators are desired.

## 5. Compiling and running with JDK 17+

In the directory containing `InvoiceApp.java`, create the `out` directory if it does not exist yet:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out InvoiceApp.java
java -cp out InvoiceApp
```

`javac` produces `out/InvoiceApp.class`. `java` starts the program and waits for user input. Try entering these lines, pressing Enter after each value:

```text
100000
2
150000
1
0
```

**Exact stdout printed by Java** (excluding user keystrokes echoed by the terminal):

```text
Unit price VND (0 to finish):
Quantity:
Item 1: 200000 VND
Unit price VND (0 to finish):
Quantity:
Item 2: 150000 VND
Unit price VND (0 to finish):
Items: 2
Subtotal: 350000 VND
Discount: 5% = 17500 VND
Total: 332500 VND
```

Manual check:

- Item 1: `100000 × 2 = 200000`.
- Item 2: `150000 × 1 = 150000`.
- Subtotal: `200000 + 150000 = 350000`.
- `350000` is between 200,000 and under 500,000 VND, so the discount is `5%`.
- Discount amount: `350000 × 5 / 100 = 17500`.
- Total due: `350000 - 17500 = 332500`.

**Running from an input file for repeatable testing:** create `sample.txt` with the exact five input lines above, then run with the appropriate syntax:

- **Linux/macOS or Windows CMD:** `java -cp out InvoiceApp < sample.txt`.
- **Windows PowerShell:** `Get-Content -LiteralPath sample.txt | java -cp out InvoiceApp`.

No Java code changes are needed to switch from keyboard input to a file/pipe: both feed data through `System.in`.

## 6. Tracing the loop with a trace table

Before running, you can build an iteration-by-iteration table to verify accumulation:

| Iteration | Unit price | Quantity | Line total | Subtotal after step | Item count after step |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 100,000 | 2 | 200,000 | 200,000 | 1 |
| 2 | 150,000 | 1 | 150,000 | 350,000 | 2 |
| 3 | 0 | Not asked | Not added | 350,000 | 2 |

On iteration 3, price `0` triggers `break`, so the program **does not ask for quantity** and adds no line item. This also helps spot a common bug: if the code still prompts for quantity after `0` is entered, `break` is in the wrong place.

After the loop, `subtotal` and `itemCount` retain their accumulated values. `lineTotal` only serves the current iteration; `subtotal` holds the total across all iterations.

## 7. Testing conditional thresholds and boundary cases

Under this exercise's policy, the table below lists the key thresholds:

| Subtotal | Discount rate | Discount via integer division | Amount due |
| ---: | ---: | ---: | ---: |
| 0 VND | 0% | 0 | 0 |
| 199,999 VND | 0% | 0 | 199,999 |
| 200,000 VND | 5% | 10,000 | 190,000 |
| 499,999 VND | 5% | 24,999 | 475,000 |
| 500,000 VND | 10% | 50,000 | 450,000 |
| 1,000,000 VND | 10% | 100,000 | 900,000 |

At 499,999 VND, `499999 * 5 / 100` equals `24999` using integer division, **not** rounded up to 25,000. Distinguish rounding policy from calculation accuracy; if the business rule changes to rounding to the nearest VND, both Process and tests must be updated together.

### Case with zero items purchased

If the first price is `0`, there are no line items:

```text
0
```

**Exact stdout:**

```text
Unit price VND (0 to finish):
Items: 0
Subtotal: 0 VND
Discount: 0% = 0 VND
Total: 0 VND
```

This is a deliberate choice in the sample contract: allowing an empty invoice with total 0. If the business rules forbid empty invoices, check `itemCount == 0` after the loop and report an error instead of printing an invoice.

### Case hitting the exact 500,000 VND threshold

Input:

```text
500000
1
0
```

**Exact stdout:**

```text
Unit price VND (0 to finish):
Quantity:
Item 1: 500000 VND
Unit price VND (0 to finish):
Items: 1
Subtotal: 500000 VND
Discount: 10% = 50000 VND
Total: 450000 VND
```

This case tests `>=` at the upper discount tier: if you mistakenly write `subtotal > 500_000`, an invoice of exactly 500,000 VND falls into the 5% tier.

## 8. Invalid inputs and program responses

Console input must never be assumed valid. In the sample program:

| Input / scenario | Behavior |
| --- | --- |
| Typing `abc` when asked for price or quantity | `Error: expected an integer` |
| Unit price `-1` or `1000001` | `Error: unit price must be from 1 to 1000000` |
| Quantity `0`, `-3`, `101` | `Error: quantity must be from 1 to 100` |
| EOF while expecting price or quantity | `Error: missing input` |
| After 100 valid lines, entering a positive price for a 101st item | `Error: too many line items` |
| Unit price `0` | Ends item entry, **not an error** |

For example, with input containing only one line `abc`:

```text
abc
```

**Exact stdout:**

```text
Unit price VND (0 to finish):
Error: expected an integer
```

With input containing a valid unit price and quantity `0`:

```text
100000
0
```

**Exact stdout:**

```text
Unit price VND (0 to finish):
Quantity:
Error: quantity must be from 1 to 100
```

These input errors are represented with `IllegalArgumentException`, which `main` catches and prints cleanly. `try-with-resources` closes `Scanner` when the program ends; in a larger application where multiple components share `System.in`, assign input stream ownership to one place instead of closing a scanner mid-run.

**Why doesn't the program re-prompt on invalid input?** That choice keeps this example focused on the item loop, discount conditionals, and validation. You can extend it into a bounded retry loop, as long as invalid data cannot loop forever or add unvalidated items.

## 9. Common programming mistakes

### 9.1. Declaring the accumulator variable inside the loop

**Logically wrong:**

```java
while (true) {
    long subtotal = 0L; // resets to 0 on every iteration
    // ... read and add amounts ...
}
```

This is only an incomplete illustrative snippet. Declare `subtotal` **before the loop** so it preserves the sum across iterations.

### 9.2. Using assignment instead of accumulation

```java
subtotal = lineTotal;  // only keeps the last item's amount
subtotal += lineTotal; // adds the new line total to the existing subtotal
```

These two lines compare two alternatives; **do not** run them back-to-back. In real code, use the second form to accumulate.

### 9.3. Wrong order of discount conditions

If you test `subtotal >= 200_000` **first** in the same `if / else if` chain, an order of 500,000 VND or more matches the 5% branch and **never reaches the 10% branch**.

Correct:

```java
if (subtotal >= 500_000L) {
    discountPercent = 10;
} else if (subtotal >= 200_000L) {
    discountPercent = 5;
} else {
    discountPercent = 0;
}
```

This is an illustrative snippet inside a method where `subtotal` and `discountPercent` are declared. Check the larger threshold first because the conditions overlap.

### 9.4. Confusing `break`, `continue`, and `return`

- `break` exits the current loop, allowing execution to move to the final total calculation.
- `continue` skips the rest of the **current iteration** and starts the next iteration; misusing it can skip validation or variable updates.
- `return` exits the currently executing method. Using `return` in `main` on price `0` skips printing the invoice afterward.

### 9.5. Using `double` and expecting every monetary amount to be exact

`double` cannot represent every decimal fraction exactly. For integer VND within modest limits, `long` is a simple choice. If invoices use fractional currency units or require exact tax/fee rules, consider **`BigDecimal`** or smallest-unit integers with an explicit rounding policy.

### 9.6. Omitting limit checks and causing overflow

With unlimited items or huge prices and quantities, `unitPrice * quantity` or `subtotal += lineTotal` could overflow `long`. The sample program protects against this with all three limits: unit price, quantity, and line count. For real applications with different bounds, recalculate the upper bound and use `Math.multiplyExact()`/`Math.addExact()` or a suitable type.

### 9.7. Stream reading bugs from mixing `nextLong()` and `nextLine()`

`Scanner.nextLong()` reads only a numeric token; a subsequent `nextLine()` can pick up the remainder of the old line. The main example uses **`nextLine()` for all reads** and `Long.parseLong()` to parse, avoiding this issue. If switching to `nextLong()`, redesign newline handling accordingly.

## 10. Controlled extensions to the exercise

Once the sample program works, you can add features one by one, always redefining Input, Process, Output, and test cases.

**Extension A — Promo code discount:** accept code `SAVE5` for an extra discount per rules. You must specify whether the code applies **before or after** the threshold discount, whether discounts stack, and whether total discount may exceed subtotal.

**Extension B — Shipping fee:** free shipping if post-discount total is at least 300,000 VND; otherwise charge 20,000 VND. Specify clearly whether the fee threshold uses the **pre- or post-discount** amount, then include the fee in Output rather than adding it ad hoc inside a print statement.

**Extension C — Retry on invalid number:** build a dedicated loop prompting for valid price/quantity with clear error messages and a stop condition. Distinguish `0` ending the cart at the **price** prompt from `0` at the **quantity** prompt, which remains invalid.

**Extension D — Fixed number of items:** if input provides the exact item count `n` upfront, a `for (int i = 0; i < n; i++)` loop is usually cleaner than `while (true)`. Still validate the domain of `n`.

**Extension E — Extracting methods:** extract discount rate logic into `discountPercentFor(long subtotal)` and final payment computation into a pure method without console I/O. This lets you test 199,999, 200,000, 499,999, and 500,000 VND directly without re-entering a full cart.

These suggestions are **extension exercises**, not part of `InvoiceApp.java`; the promised outputs in earlier examples do not depend on unimplemented features.

## 11. Checklist before finishing the practice exercise

- Have I defined inputs as **per-line unit price and quantity**, with a clear termination sentinel?
- Is price `0` checked **before** prompting for quantity?
- Are `subtotal` and `itemCount` declared **outside the loop** and updated properly on each valid item?
- Are negative prices/quantities, out-of-range values, non-numeric strings, and EOF handled?
- Did I write `if / else if / else` with **higher thresholds first, lower thresholds second**?
- Did I test an empty invoice, exact 200,000, exact 500,000, and amounts right below each threshold?
- Did I consistently apply whole-VND integer truncation for the discount amount?
- After `javac` succeeded, did I run `java` and verify **actual stdout** against the trace table and expected outputs?

**Remember:** loops handle **how many items there are**, conditionals handle **input validity and discount tiers**, and accumulator variables hold **the running subtotal after each iteration**. Separating those three responsibilities clearly makes billing programs easier to test and less error-prone.
