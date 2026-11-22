# Improving Design Incrementally with Protective Tests — Java OOP

## 1. Lesson Objectives

**Refactoring** reorganizes source-code internals to improve understandability, extensibility, and testability while **preserving promised observable behavior**. It may include extracting methods, moving responsibilities to appropriate classes, clarifying names, removing duplication, and reducing coupling.

Changing many things at once makes it hard to locate the source of failures. A safer approach uses a short cycle:

**Identify behavior → write protective tests → make a small design change → run tests → review code → repeat.**

A **protective test** (safety-net test) helps detect unintended changes to existing behavior. It cannot prove the entire system is correct, but it provides regression protection while restructuring code.

Do not confuse three kinds of change:

| Change type | Intent | What to verify |
|---|---|---|
| Refactoring | Change structure while preserving contracts | Behavioral tests pass before and after |
| Bug fix | Correct faulty behavior | A reproducing test fails before the fix and passes afterward |
| Feature change | Change or extend a contract | New tests cover requirements, existing regression tests still pass |

**Practical rule:** When a refactoring step unexpectedly fails a test, investigate and resolve the cause before continuing. Do not delete assertions just to make tests green.

## 2. What Should Protective Tests Cover?

A class's OOP contract may include:

- Return values: totals, processing status, and sorting results.
- Changed data: inventory, order state, and published counters.
- Specified exceptions/error signals: empty inputs, negative quantities, and duplicates.
- Meaningful side effects: notifications, repository writes, and payment-gateway calls.
- Boundary rules: exact discount thresholds, deadlines, 0, 1, empty inputs, and numeric limits.

By contrast, tests asserting private-helper call counts, private-field names, loop structure, or arbitrary collection implementations are often **overly coupled to implementation details**. Those details may legitimately change during refactoring.

**A test-review question:** If the algorithm changes completely but clients still receive the same results and promised effects, should the test continue to PASS? For ordinary business unit tests, usually yes.

## 3. When Legacy Code Has No Tests: Characterization Tests

Sometimes an old class needs improvement but lacks complete documentation. A **characterization test** records what it actually does, including surprises, so accidental behavior changes are detectable.

For example, a shipping-fee method currently grants free shipping at **700.000 VND or above**. Before extraction, record cases at 699.999 and 700.000 VND. If refactoring changes >= into >, the test detects the boundary error.

Note that current behavior is not always **desired** behavior. If an old bug is found, record it, clarify the requirement, and fix it separately with tests expressing the correct expectation. Do not freeze a defect merely because characterization tests pass.

Prioritize high-value scenarios: common paths, important thresholds, invalid inputs, side effects, and sensitive money/resources. Hundreds of tests are not needed before every one-line change, but risky code should not be refactored without verification.

## 4. End-to-End Example: Improving Checkout in Several Steps

Use one scenario to examine the structure **before and after**:

- An order contains line items. Each line has a product code, positive quantity, and nonnegative unit price in **whole VND**.
- **Subtotal** sums quantity × unit price; an order must contain at least one line.
- VIP customers receive a **10% subtotal** discount, rounded down using integer division, when subtotal is **at least 500.000 VND**.
- **Payable** = subtotal − discount.
- **Shipping** = 0 VND when payable is **at least 700.000 VND**; otherwise 30.000 VND.
- **Total** = payable + shipping.
- Receipts use a stable text format throughout the lesson.

The initial version combines validation, pricing, and receipt formatting in one method. The refactored version moves pricing into **PricingPolicy**, extracts **ReceiptFormatter**, and leaves **CheckoutService** to coordinate those collaborators.

~~~mermaid
flowchart LR
    subgraph Before["Trước"]
        L["LegacyCheckout: validate + calculate + format"]
    end
    subgraph After["Sau"]
        C["CheckoutService"] --> P["PricingPolicy: validate + calculate"]
        C --> F["ReceiptFormatter: format"]
    end
    T["Bộ kiểm thử hợp đồng"] --> L
    T --> C
~~~

Improvements proceed in this order:
1. Lock down outputs and failure cases with tests.
2. Extract pricing into clearly named methods.
3. Group related pricing methods into a PricingPolicy object.
4. Move formatting responsibility into ReceiptFormatter.
5. Supply CheckoutService collaborators through a constructor for a readable, replaceable workflow.
6. Run the same tests **after every step**. Remove legacy code only after confirming equivalence.

### Standalone Java 11 Program

Save everything in **SafeRefactoringDemo.java**; no external libraries are required. Both versions implement the Checkout interface. One test suite runs against both and compares results with **independently specified expectations**, preventing two equally incorrect implementations from being accepted as equivalent.

~~~java
import java.util.List;
import java.util.Objects;

public class SafeRefactoringDemo {
    static final long VIP_THRESHOLD = 500_000L;
    static final long FREE_SHIPPING_THRESHOLD = 700_000L;
    static final long SHIPPING_FEE = 30_000L;

    static final class Item {
        final String sku;
        final int quantity;
        final long unitPriceVnd;

        Item(String sku, int quantity, long unitPriceVnd) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPriceVnd = unitPriceVnd;
        }
    }

    static final class Order {
        final List<Item> items;
        final boolean vip;

        Order(List<Item> items, boolean vip) {
            this.items = items;
            this.vip = vip;
        }
    }

    static final class Quote {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;
        final String receipt;

        Quote(long subtotal, long discount,
              long shipping, long total, String receipt) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
            this.receipt = receipt;
        }
    }

    interface Checkout {
        Quote quote(Order order);
    }

    // TRƯỚC: một method phải kiểm tra, tính toán, định dạng.
    static final class LegacyCheckout implements Checkout {
        @Override
        public Quote quote(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.quantity <= 0
                        || item.unitPriceVnd < 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineAmount = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineAmount);
            }

            long discount = order.vip && subtotal >= VIP_THRESHOLD
                    ? subtotal / 10L : 0L;
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = payable >= FREE_SHIPPING_THRESHOLD
                    ? 0L : SHIPPING_FEE;
            long total = Math.addExact(payable, shipping);

            String receipt = "subtotal=" + subtotal
                    + ";discount=" + discount
                    + ";shipping=" + shipping
                    + ";total=" + total;

            return new Quote(
                    subtotal, discount, shipping, total, receipt);
        }
    }

    // Đối tượng giá trị trung gian: kết quả tính tiền đã hoàn tất.
    static final class Pricing {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;

        Pricing(long subtotal, long discount,
                long shipping, long total) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
        }
    }

    // SAU bước tách: quy tắc giá được gom vào một lớp.
    static final class PricingPolicy {
        Pricing calculate(Order order) {
            long subtotal = calculateSubtotal(order);
            long discount = calculateDiscount(subtotal, order.vip);
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = calculateShipping(payable);
            long total = Math.addExact(payable, shipping);

            return new Pricing(subtotal, discount, shipping, total);
        }

        private long calculateSubtotal(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.quantity <= 0
                        || item.unitPriceVnd < 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineAmount = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineAmount);
            }
            return subtotal;
        }

        private long calculateDiscount(long subtotal, boolean vip) {
            return vip && subtotal >= VIP_THRESHOLD
                    ? subtotal / 10L : 0L;
        }

        private long calculateShipping(long payable) {
            return payable >= FREE_SHIPPING_THRESHOLD
                    ? 0L : SHIPPING_FEE;
        }
    }

    // SAU bước tách: định dạng là một trách nhiệm độc lập.
    static final class ReceiptFormatter {
        String format(Pricing pricing) {
            return "subtotal=" + pricing.subtotal
                    + ";discount=" + pricing.discount
                    + ";shipping=" + pricing.shipping
                    + ";total=" + pricing.total;
        }
    }

    // SAU: class điều phối sử dụng composition và constructor injection.
    static final class CheckoutService implements Checkout {
        private final PricingPolicy pricing;
        private final ReceiptFormatter formatter;

        CheckoutService(PricingPolicy pricing,
                        ReceiptFormatter formatter) {
            this.pricing = Objects.requireNonNull(pricing);
            this.formatter = Objects.requireNonNull(formatter);
        }

        @Override
        public Quote quote(Order order) {
            Pricing result = pricing.calculate(order);
            return new Quote(
                    result.subtotal,
                    result.discount,
                    result.shipping,
                    result.total,
                    formatter.format(result));
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    // Kỳ vọng nghiệp vụ độc lập với cả hai implementation.
    private static void expectQuote(
            Checkout checkout, Order order,
            long subtotal, long discount,
            long shipping, long total) {
        Quote actual = checkout.quote(order);
        String expectedReceipt = "subtotal=" + subtotal
                + ";discount=" + discount
                + ";shipping=" + shipping
                + ";total=" + total;

        check(actual.subtotal == subtotal, "Unexpected subtotal");
        check(actual.discount == discount, "Unexpected discount");
        check(actual.shipping == shipping, "Unexpected shipping");
        check(actual.total == total, "Unexpected total");
        check(expectedReceipt.equals(actual.receipt),
                "Unexpected receipt text");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    private static void expectOverflow(Runnable action) {
        try {
            action.run();
        } catch (ArithmeticException expected) {
            return;
        }
        throw new AssertionError("Expected ArithmeticException");
    }

    // CÙNG bộ test bảo vệ được chạy cho cả code cũ và code mới.
    private static void contractTests(Checkout checkout) {
        // Khách thường: 100.000 + 30.000 shipping = 130.000.
        expectQuote(checkout,
                new Order(List.of(new Item("PEN", 1, 100_000L)), false),
                100_000L, 0L, 30_000L, 130_000L);

        // VIP đúng ngưỡng giảm giá:
        // subtotal 500.000, discount 50.000,
        // payable 450.000, shipping 30.000 -> total 480.000.
        expectQuote(checkout,
                new Order(List.of(new Item("BOOK", 2, 250_000L)), true),
                500_000L, 50_000L, 30_000L, 480_000L);

        // VIP subtotal 800.000, discount 80.000,
        // payable 720.000 nên miễn phí shipping.
        expectQuote(checkout,
                new Order(List.of(new Item("BOOK", 2, 400_000L)), true),
                800_000L, 80_000L, 0L, 720_000L);

        // Khách thường, payable 699.999 vẫn chịu phí.
        expectQuote(checkout,
                new Order(List.of(new Item("A", 1, 699_999L)), false),
                699_999L, 0L, 30_000L, 729_999L);

        // Đúng ngưỡng 700.000: miễn phí, bắt lỗi đổi >= thành >.
        expectQuote(checkout,
                new Order(List.of(new Item("A", 1, 700_000L)), false),
                700_000L, 0L, 0L, 700_000L);

        expectInvalid(() -> checkout.quote(null));
        expectInvalid(() -> checkout.quote(new Order(List.of(), false)));
        expectInvalid(() -> checkout.quote(new Order(
                List.of(new Item("A", 0, 100L)), false)));
        expectInvalid(() -> checkout.quote(new Order(
                List.of(new Item("A", 1, -10L)), false)));

        // Math.addExact phải phát hiện tổng vượt phạm vi long.
        expectOverflow(() -> checkout.quote(new Order(List.of(
                new Item("A", 1, Long.MAX_VALUE),
                new Item("B", 1, 1L)), false)));
    }

    public static void main(String[] args) {
        Checkout legacy = new LegacyCheckout();
        Checkout refactored = new CheckoutService(
                new PricingPolicy(), new ReceiptFormatter());

        contractTests(legacy);
        contractTests(refactored);

        System.out.println(
                "PASS: same 5 business cases and 5 error cases in both versions");
    }
}
~~~

Run in a terminal from the file's directory:

~~~bash
javac SafeRefactoringDemo.java
java SafeRefactoringDemo
~~~

Output if all assertions pass:

~~~text
PASS: same 4 business cases and 5 error cases in both versions
~~~

For each implementation, the program has **5 pricing scenarios and 5 failure scenarios**: 4 invalid-input cases and 1 overflow case. Expectations are specified directly in tests rather than copied from legacy code, so the tests verify both equivalence and the stated business rules.

Math.multiplyExact, Math.addExact, and Math.subtractExact make overflow detectable. For currencies with fractional units, use an appropriate type such as BigDecimal and a documented rounding policy; the example intentionally uses whole VND for simplicity and consistency.

## 5. Concrete Improvement Sequence

| Step | Small change | Immediate verification |
|---|---|---|
| 0 | Rerun legacy code with protective tests | Stable passing tests and explicit expectations for important cases |
| 1 | Give subtotal, discount, and payable variables clear names | Results/exceptions unchanged |
| 2 | Extract calculateSubtotal from the large method | Invalid-input behavior, sums, and overflow unchanged |
| 3 | Extract calculateDiscount and calculateShipping | Thresholds at 500.000 and 700.000 preserved |
| 4 | Group related pricing methods in PricingPolicy | Values and promised error ordering unchanged |
| 5 | Extract ReceiptFormatter | Receipt format remains unchanged unintentionally |
| 6 | Inject dependencies into CheckoutService through its constructor | Callers still receive the same contractual Quote |
| 7 | Remove obsolete implementations and simplify names/visibility | Rerun tests, review diffs, and check integrations where needed |

~~~mermaid
flowchart TD
    A["Xác định hợp đồng và rủi ro"] --> B["Viết hoặc cập nhật test bảo vệ"]
    B --> C["Chọn một cải thiện thiết kế nhỏ"]
    C --> D["Biên dịch và chạy test"]
    D --> E{"Mọi test liên quan đều đạt?"}
    E -- "Không" --> F["Điều tra thay đổi hành vi hoặc test quá chặt"]
    F --> C
    E -- "Có" --> G["Review diff, đặt tên và trách nhiệm"]
    G --> H{"Còn cải thiện có ích?"}
    H -- "Có" --> C
    H -- "Không" --> I["Kết thúc refactor và kiểm thử tích hợp phù hợp"]
~~~

Note: The test suite may not protect branches that have never been exercised. Coverage reveals unexecuted code, but **100% line coverage does not guarantee correct assertions or coverage of every business rule**.

## 6. Designing Tests That Do Not Break Needlessly During Refactoring

**Verify public results and effects.** For pricing classes, focus on monetary amounts. For receipt senders, verify the right recipient, content, and timing under the contract.

**Name tests after behavior.** For example, vipDiscountStartsAtThreshold or failedPaymentDoesNotSendReceipt is clearer than testCallsCalculateDiscountTwice.

**Do not freeze irrelevant helper ordering.** Replacing for loops with Stream or HashMap with another structure should not fail business tests when contractual results and guarantees stay the same.

**Use test doubles for the right purpose.** Fake repositories test logic against in-memory data; stubs control payment-gateway results; mocks are appropriate when the external interaction itself is required behavior. They do not replace integration tests with real databases, queues, or APIs.

**Keep tests readable, independent, and repeatable.** Avoid real clocks, randomness, or networks in unit tests unless they are the subject of testing. Inject java.time.Clock, random generators, and collaborators to control inputs.

**Do not compare only old and new outputs.** If the legacy version contains a bug, both may return the same wrong result. Combine before/after comparisons with **independent expected values** derived from requirements and worked examples.

## 7. Refactoring Side Effects Requires Extra Care

The pricing example is nearly pure, but real methods often open transactions, write to databases, send emails, or call payment gateways.

If the original order was:
1. Validate and check inventory.
2. Charge payment.
3. Persist the order.
4. Request a confirmation email.

Extracting methods/classes **must not accidentally** change rules such as "do not email after failed payment" or move transaction boundaries. Test:
- Persisted state and consistency after success or failure.
- External calls that must or must not occur under business rules.
- Truly meaningful ordering, idempotency, and retries where required.
- Contracts between application services and real adapters through integration tests.

Illustrative Mockito + JUnit 5 example, assuming CheckoutService and the interfaces already exist in a real application:

~~~java
when(gateway.charge(orderId, amountVnd)).thenReturn(false);

CheckoutResult result = checkoutService.checkout(orderId);

assertEquals(CheckoutResult.PAYMENT_DECLINED, result);
verifyNoInteractions(receiptSender);
~~~

This is **meaningful interaction verification** because "do not send a receipt when payment fails" is contractual behavior. It differs from checking how many times an internal private helper runs.

## 8. Common Mistakes When Improving Design

| Mistake | Consequence | Mitigation |
|---|---|---|
| Changing business formulas while extracting classes | Difficult to distinguish regressions from feature changes | Separate the changes and test each one |
| Moving hundreds of lines at once | Hard to locate failures | Make small, independently verified transformations |
| Deleting failing tests without investigating | Regressions may be missed | Determine whether the test protects a contract or merely implementation details |
| Measuring only line coverage | False confidence in completeness | Add boundary and failure tests with specific assertions |
| Creating too many one-line classes/methods | Increased fragmentation and coupling | Extract according to actual responsibilities and reasons to change |
| Making private fields public to refactor faster | Breaks encapsulation | Pass data through suitable constructors, methods, or value objects |
| Changing validation order | Different exceptions or side effects | Document and test observable ordering when contractual |
| Assuming a fake perfectly simulates a database | Constraint, transaction, and concurrency defects go undetected | Add integration tests |
| Tests relying on current dates or random IDs | Unstable tests | Inject Clock/ID generators and use fixed values |

**Note on ordering and failures:** If input contains two separate defects, changing validation order can change which exception occurs first. This may be observable behavior; establish the requirements before declaring the reordering safe.

## 9. Organizing Refactoring Work in Real Code

For part of a running system, follow this process:

**Step A — Scope the work and establish a baseline.** Choose one clear responsibility, inspect callers, record existing tests, and identify behavior to preserve. For legacy code, write characterization tests based on current input/output or side effects. Confirm tests are stable before editing.

**Step B — Analyze change points.** A class bloated with validation, pricing, persistence, and presentation often has multiple reasons to change. Identify data flow, object lifecycles, and transaction boundaries. Choose the smallest extraction that improves clarity.

**Step C — Change one thing at a time.** Rename variables, extract methods, move methods, or extract classes. Complete a transformation, compile/test, then continue. Use IDE refactoring tools when convenient, but inspect diffs because the IDE cannot verify every business rule.

**Step D — Refine tests once architecture is clear.** Test public behavior without tightly coupling tests to new helpers. Organize unit/integration tests around responsibility boundaries. Avoid duplicating the entire suite just to test every extracted class.

**Step E — Final verification.** Confirm that no obsolete code path remains implicitly used, public APIs have only intended changes, tests pass, and side effects are verified. If behavior must change, handle it separately with tests expressing the new expectations.

There is no need to wait for the entire system to be "clean" before developing further. Effective refactoring consists of **small, purposeful, evidence-backed steps** near code that needs to change.

## 10. Practice Exercises

**Exercise 1 — Detect a Threshold Bug:** In PricingPolicy, change the free-shipping rule from greater than or equal to 700.000 to greater than 700.000. Add a standard-customer case with subtotal exactly 700.000, expecting shipping = 0. The test must detect the bug.

**Exercise 2 — Detect a Discount Bug:** Change the VIP threshold from greater than or equal to 500.000 to greater than 500.000. The test case with VIP subtotal 500.000 must FAIL.

**Exercise 3 — Extract Method:** Starting with LegacyCheckout, extract validation, subtotal, discount, and shipping logic, then rerun contractTests after every extraction. Record how errors and results remain unchanged.

**Exercise 4 — Extract Class:** Move receipt formatting into a separate class. Then change receipt-format requirements separately and explain why PricingPolicy does not need to change. That is a separate feature change, not a behavior-preserving refactoring.

**Exercise 5 — Characterization Test for a Legacy Bug:** Suppose the old system miscalculates fees for a special case. Write a test reproducing current behavior to protect extraction, then specify the correct expectation in a new bug-fix test and fix it separately.

**Exercise 6 — Integration Boundary:** Sketch a fake PaymentGateway and mock ReceiptSender; prove rejected payments never trigger receipt delivery. Identify additional integration tests needed to verify that the real payment adapter handles failure codes correctly.

## 11. Knowledge Self-Check

1. Why is comparing old and new implementations insufficient when the old one has a bug?
2. Why can tests asserting private-helper call counts prevent legitimate refactoring?
3. When is collaborator interaction order part of a contract?
4. After extracting PricingPolicy and ReceiptFormatter, why should CheckoutService remain the coordinator?
5. If a change causes a failing test, how can you distinguish a business regression from an overly implementation-coupled test?

**Key takeaway:** Protective tests provide fast feedback while improving structure, but the strength of that safety net depends on **which behaviors the tests actually verify**. Refactor in small steps, maintain clear OOP responsibility boundaries, check immediately after each change, and protect normal cases, edge cases, failures, and meaningful side effects.
