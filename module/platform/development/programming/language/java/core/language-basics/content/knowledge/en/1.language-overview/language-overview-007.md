# Distinguishing Valid Syntax from Correct Business Results

## 1. Why Can a Runnable Program Still Be Wrong?

Consider the following two Java snippets:

~~~java
int quantity = 3;
int unitPrice = 100_000;
int subtotal = quantity * unitPrice;
System.out.println(subtotal); // 300000
~~~

~~~java
int quantity = 3;
int unitPrice = 100_000;
int subtotal = quantity + unitPrice;
System.out.println(subtotal); // 100003
~~~

Both snippets are **syntactically valid**, well-typed, and compile cleanly. Yet if the requirement is **subtotal = quantity × unit price**, only the first snippet implements the business rule correctly.

The crucial point to remember: **`javac` can check many rules of the Java language, but it does not automatically know what the user wants to compute**. A program can compile successfully and throw no exceptions while still returning wrong results, miscalculating money, or violating the problem's constraints.

This lesson focuses on how to go from a **verbal requirement** to **verifiable rules**, write correct Java code, and test the results. No framework or database is needed to practice.

## 2. Four Layers of Correctness Checking

| Check Layer | Question | Example Issue | How It Is Detected |
|---|---|---|---|
| **Syntax** | Does the code follow Java grammar? | Missing `;`, unclosed brace | `javac` reports a compile error |
| **Static semantics / types** | Are variables, operations, and return types valid? | `int n = "ba";` | Compiler type checking |
| **Runtime behavior** | Do exceptions or failures occur when running? | Integer division by 0, out-of-bounds array access | Running, testing, logs, stack trace |
| **Business correctness** | Do the results and behavior match the agreed rules? | Wrong customer discount, wrong free-shipping threshold | Acceptance tests, expected examples, requirement verification |

All first three conditions are necessary in many applications, yet **they are not sufficient to guarantee the fourth condition**.

~~~mermaid
flowchart TD
    A["Business requirement"] --> B["Verifiable rules"]
    B --> C["Write Java code"]
    C --> D{"Compiles successfully?"}
    D -->|"No"| E["Fix syntax / types"]
    E --> C
    D -->|"Yes"| F["Execute and test"]
    F --> G{"Results match rules?"}
    G -->|"No"| H["Find logic / assumption / data bug"]
    H --> B
    G -->|"Yes"| I["Passed checked cases; continue review and further testing"]
~~~

Even when a test suite is all green, that only proves the program **passes the checked cases**, not that every input and every environment are error-free.

## 3. Turning Verbal Requirements into a Clear Contract

Suppose a store sells goods in **whole Vietnamese dong** and sets the following policy:

- **BR-01 – Valid data:** unit price must be **greater than 0**; quantity must be **greater than 0**.
- **BR-02 – Goods subtotal:** `subtotal = unitPrice × quantity`.
- **BR-03 – Discount:** customers who are **active members** with an initial subtotal **of 200,000 dong or more** receive a **10% discount on the subtotal**. All other cases receive no discount.
- **BR-04 – Rounding:** the discount amount **takes the integer part in dong** (rounded down); inputs and results are non-negative.
- **BR-05 – Shipping:** if the **subtotal after discount** is **300,000 dong or more**, shipping is 0; if lower, the fee is **30,000 dong**.
- **BR-06 – Total payable:** `payable = subtotal − discount + shipping`.
- **BR-07 – Numeric overflow:** if any calculation exceeds the `long` range, it must report an error instead of silently producing a wrong amount.

**Easy-to-miss detail:** the discount threshold checks `subtotal` **before discount**, whereas the free-shipping threshold checks the amount **after discount**. Both thresholds use “**from ... or more**”, meaning `>=`, not `>`.

Rounding rules are part of the requirement: for a 10% discount and non-negative whole dong, `subtotal / 10` (integer division) gives the discount rounded down. If the policy changes to 7.5% or adds taxes, the formula and rounding rules must be re-confirmed.

### Prediction Table Before Writing Code

| Subtotal | Active member? | Discount | After discount | Shipping | Total payable |
|---:|---|---:|---:|---:|---:|
| 199,999 | Yes | 0 | 199,999 | 30,000 | 229,999 |
| 200,000 | Yes | 20,000 | 180,000 | 30,000 | 210,000 |
| 300,000 | Yes | 30,000 | 270,000 | 30,000 | 300,000 |
| 300,000 | No | 0 | 300,000 | 0 | 300,000 |
| 400,000 | Yes | 40,000 | 360,000 | 0 | 360,000 |

This table is a **test oracle**: expected results are derived from the rules before seeing what the program returns.

## 4. A Valid Java Snippet That Violates Business Rules

The following snippet is syntactically valid, yet checks the shipping fee using the subtotal **before** discount:

~~~java
long subtotal = 300_000L;
boolean activeMember = true;

long discount = activeMember && subtotal >= 200_000L
        ? subtotal / 10
        : 0L;

long shipping = subtotal >= 300_000L ? 0L : 30_000L; // VIOLATES RULE
long payable = subtotal - discount + shipping;

System.out.println(payable); // 270000
~~~

According to BR-05, it must check `subtotal - discount = 270000`, so the shipping fee is `30000` and the right total is **300000**. `javac` cannot infer rule BR-05 from a snippet of code.

Minimal fix:

~~~java
long afterDiscount = subtotal - discount;
long shipping = afterDiscount >= 300_000L ? 0L : 30_000L;
long payable = afterDiscount + shipping;
System.out.println(payable); // 300000
~~~

**Warning:** the snippets above focus on illustrating logic bugs; a complete implementation still needs input guards, overflow checks, and threshold tests.

## 5. A Standalone, Runnable Java 17 Program

Create a file named exactly **`BusinessCorrectnessDemo.java`**:

~~~java
public final class BusinessCorrectnessDemo {
    private static final long DISCOUNT_MIN = 200_000L;
    private static final long FREE_SHIPPING_MIN = 300_000L;
    private static final long SHIPPING_FEE = 30_000L;

    private BusinessCorrectnessDemo() {}

    // Record only stores the result; all amounts are in whole dong.
    record Quote(long subtotal, long discount,
                 long shipping, long payable) {}

    static Quote calculate(long unitPrice, int quantity,
                           boolean activeMember) {
        if (unitPrice <= 0) {
            throw new IllegalArgumentException("Don gia phai duong");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("So luong phai duong");
        }

        // Detect long overflow before obtaining subtotal.
        long subtotal = Math.multiplyExact(unitPrice, (long) quantity);

        // 10% and rounded down to whole dong, only when both conditions hold.
        long discount = activeMember && subtotal >= DISCOUNT_MIN
                ? subtotal / 10
                : 0L;

        long afterDiscount = Math.subtractExact(subtotal, discount);
        long shipping = afterDiscount >= FREE_SHIPPING_MIN
                ? 0L
                : SHIPPING_FEE;
        long payable = Math.addExact(afterDiscount, shipping);

        return new Quote(subtotal, discount, shipping, payable);
    }

    static void expect(String label, long unitPrice, int quantity,
                       boolean member, long expectedSubtotal,
                       long expectedDiscount, long expectedShipping,
                       long expectedPayable) {
        Quote q = calculate(unitPrice, quantity, member);
        if (q.subtotal() != expectedSubtotal
                || q.discount() != expectedDiscount
                || q.shipping() != expectedShipping
                || q.payable() != expectedPayable) {
            throw new AssertionError(
                    label + ": ket qua khong dung, actual=" + q);
        }
        System.out.println(label + " -> " + q.payable() + " VND");
    }

    static void checkInvalidInput() {
        boolean invalidPrice = false;
        boolean invalidQuantity = false;
        try {
            calculate(0, 1, false);
        } catch (IllegalArgumentException expected) {
            invalidPrice = true;
        }
        try {
            calculate(100, 0, true);
        } catch (IllegalArgumentException expected) {
            invalidQuantity = true;
        }
        if (!invalidPrice || !invalidQuantity) {
            throw new AssertionError("Input invalid was accepted");
        }
        System.out.println("Invalid input: PASS");
    }

    static void checkOverflow() {
        boolean overflowDetected = false;
        try {
            calculate(Long.MAX_VALUE, 2, true);
        } catch (ArithmeticException expected) {
            overflowDetected = true;
        }
        if (!overflowDetected) {
            throw new AssertionError("Overflow was not detected");
        }
        System.out.println("Overflow: PASS");
    }

    public static void main(String[] args) {
        expect("A", 100_000, 3, true,
                300_000, 30_000, 30_000, 300_000);
        expect("B", 100_000, 3, false,
                300_000, 0, 0, 300_000);
        expect("C", 199_999, 1, true,
                199_999, 0, 30_000, 229_999);
        expect("D", 200_000, 1, true,
                200_000, 20_000, 30_000, 210_000);
        expect("E", 100_000, 4, true,
                400_000, 40_000, 0, 360_000);
        checkInvalidInput();
        checkOverflow();
        System.out.println("ALL CASES PASS");
    }
}
~~~

The program requires **JDK 17 or later** because it uses `record`. Open a terminal in the directory containing the file and run:

~~~bash
javac --release 17 -encoding UTF-8 BusinessCorrectnessDemo.java
java BusinessCorrectnessDemo
~~~

**Expected output:**

~~~text
A -> 300000 VND
B -> 300000 VND
C -> 229999 VND
D -> 210000 VND
E -> 360000 VND
Invalid input: PASS
Overflow: PASS
ALL CASES PASS
~~~

The code uses `if`, `&&`, the ternary operator `?:`, integer arithmetic, and methods to verify the rules. The `throw` statements at the input boundary only reject bad data; they do not replace testing the subtotal formula.

**Note on testing:** the `expect` method throws `AssertionError` directly on mismatch, so it does not depend on the `-ea` flag. The outputs shown in this lesson are **expectations for learners to run and verify themselves**, not a claim that code was executed on the learner's machine.

## 6. Reading Code in Business Order

Trace the case `unitPrice = 100000`, `quantity = 3`, `activeMember = true`:

| Step | Calculation/Condition | Result |
|---|---|---:|
| 1 | Check that unit price and quantity are positive | Valid |
| 2 | `100000 × 3` | `subtotal = 300000` |
| 3 | Active member and `300000 >= 200000` | Eligible |
| 4 | `300000 / 10` | `discount = 30000` |
| 5 | `300000 - 30000` | `afterDiscount = 270000` |
| 6 | `270000 >= 300000` | False |
| 7 | Add shipping fee `30000` | `payable = 300000` |

In step 6, if someone accidentally uses `subtotal` instead of `afterDiscount`, the program remains syntactically valid and well-typed, yet violates BR-05.

**Important principle:** choose variable names that reflect the **meaning and stage** of the data. `subtotal` and `afterDiscount` are both `long`, yet they cannot substitute for each other in every formula merely because they share the same Java type.

## 7. Testing Thresholds and Edge Cases

Business bugs frequently appear at **condition boundaries**, on invalid data, or when conditions combine.

| Situation | Test Data | Result to Confirm |
|---|---|---|
| Just below discount threshold | `subtotal = 199999`, member=true | No discount |
| Exactly at discount threshold | `subtotal = 200000`, member=true | 10% discount applies |
| Same amount, non-member | `subtotal = 200000`, member=false | No discount |
| After discount just below shipping threshold | `subtotal = 300000`, member=true | After discount 270000, fee 30000 |
| Exactly at shipping threshold | `subtotal = 300000`, member=false | Shipping 0 |
| After discount above shipping threshold | `subtotal = 400000`, member=true | Shipping 0 |
| Zero or negative quantity | `quantity <= 0` | Input rejected |
| Zero or negative unit price | `unitPrice <= 0` | Input rejected |
| Multiplication overflow | `unitPrice = Long.MAX_VALUE`, `quantity = 2` | `ArithmeticException` |
| Subtotal 200,001 and member=true | `subtotal = 200001` | Discount 20,000 dong (integer part) |

When testing a threshold `T`, people commonly pick **`T - 1`, `T`, `T + 1`** in meaningful units. For BR-05, make sure to construct data so that the **after-discount amount** lands on these points; testing only the pre-discount subtotal can let bugs slip through.

### Additional Properties That Can Be Checked

For valid inputs without numeric overflow, every result must satisfy:

- `subtotal > 0`.
- `0 <= discount <= subtotal`.
- `shipping == 0` or `shipping == 30000`.
- `payable == subtotal - discount + shipping`.
- If `activeMember == false`, then `discount == 0`.
- If `afterDiscount >= 300000`, then `shipping == 0`; if smaller, then `shipping == 30000`.

These properties are great for reviewing many cases; however, a buggy implementation might still preserve several properties, so combine them with **concrete example outputs confirmed from the business rules**.

## 8. Java Pitfalls That Cause Incorrect Business Results

### 8.1. Integer Division and Unclear Rounding

~~~java
int percent = 15;
int amount = 101;
int discount = amount * percent / 100; // 15, remainder is truncated
~~~

This formula can be right **or wrong** depending on the required rounding policy. For money, you must agree on units, division, rounding order, and rounding policy. `double` cannot represent many decimal numbers exactly; whole numbers in the smallest unit or `BigDecimal` are usually easier to control.

### 8.2. Numeric Overflow Is Still Type-Valid `long`

~~~java
long price = Long.MAX_VALUE;
long total = price * 2; // long overflow with ordinary multiplication
~~~

Java does not automatically throw an exception when ordinary integer operations overflow. Use `Math.multiplyExact`/`Math.addExact` or enforce explicit data bounds when overflow is disallowed.

### 8.3. Confusing `>` with `>=`

~~~java
boolean eligible = subtotal > 200_000;  // Wrong when subtotal is exactly 200000
boolean correct = subtotal >= 200_000; // Correct for "from 200000"
~~~

A single character difference can cause thousands of near-threshold transactions to fail.

### 8.4. `==` Does Not Compare the Contents of Two Strings

~~~java
String role = new String("MEMBER");
System.out.println(role == "MEMBER");      // false
System.out.println("MEMBER".equals(role));  // true
~~~

If a discount condition relies on a role read from input, using `==` with `String` can break logic even though it compiles and runs normally. Calling `"MEMBER".equals(role)` is also safe when `role == null`.

### 8.5. `&&` and `&` Are Not Completely Identical

~~~java
String memberId = null;
boolean valid = memberId != null && !memberId.isBlank(); // false
~~~

`&&` short-circuits: when the left side is false, the right side is not evaluated. Switching to `&` on booleans evaluates both sides, which here causes `NullPointerException`.

### 8.6. Right Condition, Checked at the Wrong Stage

The rule “free shipping from 300,000 dong **after discount**” must use `afterDiscount`. Even though `subtotal`, `afterDiscount`, and `payable` all have type `long`, they represent different stages. Variable names and calculation order must reflect the policy.

### 8.7. Input Validation Does Not Replace Output Verification

Positive unit price and quantity **do not guarantee** that multiplication will not overflow. Conversely, obtaining a total amount does not prove the buyer qualified for a discount. You must verify **input conditions, arithmetic boundaries, and business results**.

## 9. Debugging Process When a Test Fails

When results do not match requirements, do not tweak things randomly until tests turn green. Try step by step:

1. **Re-read the requirement sentence:** identify thresholds, inclusive equality, eligible parties, calculation stage, units, and rounding rules.
2. **Write the expected result by hand** from the rules. For problems with multiple conditions, draw a decision table.
3. **Reproduce with the smallest case:** for instance, `subtotal=300000`, member=true is enough to catch using the pre-discount shipping threshold.
4. **Inspect intermediate values:** `subtotal`, `discount`, `afterDiscount`, `shipping`, `payable`.
5. **Check operators, types, and evaluation order:** especially `>=`, `&&`, integer division, and overflow.
6. **Fix the exact rule that was violated**, add a regression test for the case just found, and re-run existing cases.

A bug can also stem from an **unclear specification**. If the requirement does not state how discounts are rounded, the programmer should not assume one way and treat the result as correct; clarify with the business owner.

## 10. Verification Toolkit: Each Tool Answers One Question

| Activity | What It Verifies | What It Does Not Guarantee |
|---|---|---|
| `javac` | Syntax, types, names, compilation rules | That the pricing formula is right |
| Running the program | Behavior observed on the executed inputs | Correctness on all other inputs |
| Unit tests / explicit assertions | One specific rule with given inputs and expected values | Full business coverage |
| Boundary testing | Cases just below, at, and above thresholds | All combinations of rules |
| Code review against BR | Re-checking units, formulas, branches, exceptions | Replacing actual test runs |
| Static analysis / lint | Certain bug patterns and quality issues | Understanding all business policies |
| Integration/acceptance tests | Components working together and realistic scenarios | Covering infinitely many system states |

When using Java's `assert` keyword in ordinary programs, remember assertions can be **disabled** unless `-ea` is enabled. Therefore, the example uses `AssertionError` directly in its test methods so mismatches are always caught when running the demo. In real projects, use a testing framework with properly managed assertions.

## 11. Practice Exercises with Answers

### Exercise A — Find the Business Bug in Valid Code

~~~java
long subtotal = 300_000;
long discount = 30_000;
long shipping = subtotal >= 300_000 ? 0 : 30_000;
long payable = subtotal - discount + shipping;
~~~

**Question:** Does the code compile (when placed inside a valid method)? Does the result satisfy BR-05?

**Answer:** the code has valid syntax and types; `payable=270000`, yet BR-05 requires the shipping fee to be based on `270000` after discount, so the right total is `300000`. Fix the condition to `subtotal - discount >= 300_000` or introduce a variable named `afterDiscount` and use it.

### Exercise B — Check Boundaries

For the same active customer, compute the results for subtotals `199999`, `200000`, and `200001`.

**Answer:** respectively:

- 199999: discount 0, shipping 30000, payable **229999**.
- 200000: discount 20000, after discount 180000, shipping 30000, payable **210000**.
- 200001: discount 20000 after rounding down, after discount 180001, shipping 30000, payable **210001**.

### Exercise C — Spot Missing Tests

A team only tested `subtotal=400000` and saw that a member got a discount, free shipping, and the right total. Has BR-05 been proven?

**Answer:** not yet. You need the case `subtotal=300000, activeMember=true`: after discount it becomes 270000, so **free shipping does not apply**. This is the case that catches “shipping checked before discount”.

### Exercise D — Test Invalid Data and Overflow

Run `calculate(0,1,false)`, `calculate(100,0,true)`, `calculate(Long.MAX_VALUE,2,true)`.

**Answer:** the first two cases throw `IllegalArgumentException` for violating BR-01; the last case throws `ArithmeticException` because `Math.multiplyExact` detects overflow. You must not replace errors with negative prices and keep calculating fees.

### Exercise E — Policy Change

The store owner changes the condition: “free shipping from 300,000 dong **before discount**”. What needs to be updated?

**Answer:** in the new BR-05, the threshold uses `subtotal` instead of `afterDiscount`. You must update the code, the expected values in affected cases (especially subtotal 300000 with a discount), and record the specification change. A fix for a new BR may **intentionally differ** from the old test suite's results: tests must also be updated with justification, never silently tweaked just to make them green.

## 12. Acceptance Checklist and Takeaways

- [ ] Distinguish **compile-time errors**, **runtime errors**, and **business logic bugs**.
- [ ] Turn business rules into input preconditions, formulas, and expected results.
- [ ] Know how to identify which values belong before vs. after a processing step.
- [ ] Verify thresholds `<`, `<=`, `>`, `>=` and condition combinations accurately.
- [ ] Use appropriate numeric types and currency units; define rounding rules.
- [ ] Guard against invalid inputs, overflow, and exception-prone branches.
- [ ] Compile and run `BusinessCorrectnessDemo.java`, verifying the output.
- [ ] Include cases **below threshold, at threshold, above threshold**, for both members and non-members.
- [ ] Have regression tests proving that a fixed business bug does not return.
- [ ] Never treat “`javac` reported no error” or “ran without crashing” as sufficient proof of business correctness.

**Conclusion:** Java decides **whether code is valid according to the language**; business rules define **which results are right**. To build reliable software, bridge both sides with input/output examples, clearly named calculations, edge-case handling, and tests verified against requirements.
