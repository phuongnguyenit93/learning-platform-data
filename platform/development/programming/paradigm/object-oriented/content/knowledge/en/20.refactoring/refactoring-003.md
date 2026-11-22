# Extracting Methods and Classes (Extract Method / Extract Class) in Java OOP

## 1. Why Extract Code?

As a method grows, it often accumulates multiple jobs: validating data, calculating values, updating state, generating notifications, and calling external services. When a class contains too many distinct responsibility groups, even a small change forces developers to read, modify, and test the entire class.

**Refactoring** improves internal structure while **preserving observable behavior**. Two foundational techniques are:

- **Extract Method:** Select a cohesive block of statements, move it into a method whose name expresses its purpose, and replace the original block with a call to that method.
- **Extract Class:** Move related data and behavior with a distinct responsibility into a new class; the original class delegates through a clear API.

The techniques can be combined: first extract steps from a long method, then identify methods that belong to another class's responsibility and move them there.

**Expected outcome:** More readable code, clearer responsibilities, and easier reuse and testing, while preserving promised return values, exceptions, side effects, and business rules.

| Criterion | Extract Method | Extract Class |
|---|---|---|
| Signal | A method performs several semantically distinct steps | A class has several groups of reasons to change |
| Action | Move code into a clearly named method | Move related fields/methods into another object |
| Scale | Mostly reorganizes a class's internals | Redistributes responsibilities among objects |
| Example | Extract calculateSubtotal and applyDiscount | Extract PricingPolicy and ReceiptFormatter from CheckoutService |
| Common pitfalls | Too many trivial methods, excessive parameters, changed side-effect order | Meaningless classes, exposed data, circular dependencies, excessive fragmentation |

## 2. Signals That Extraction May Help

Useful signals, not absolute rules:

1. Understanding one business operation requires reading many lines.
2. Different blocks in the same method have distinct purposes: *validate → calculate → format → persist*.
3. One class changes for unrelated reasons, such as changes to pricing rules **or** invoice presentation.
4. Several methods share a group of fields but hardly use the rest of the class; they form a distinct cohesive group.
5. Testing one small rule requires constructing many unrelated dependencies.

Length is only a **signal**. A clear 40-line method describing a linear algorithm may be easier to maintain than 10 fragmented methods. Aim for greater **cohesion**, lower coupling, and clear business meaning and data flow.

## 3. Extract Method: A Step-by-Step Approach

Suppose a checkout method contains all order logic:

~~~java
// Phác thảo cấu trúc ban đầu:
CheckoutResult checkout(Order order) {
    // (1) Kiểm tra đơn hàng
    // (2) Cộng giá trị từng dòng
    // (3) Tính giảm giá VIP
    // (4) Tính phí vận chuyển
    // (5) Định dạng chuỗi biên nhận
    // (6) Trả kết quả
}
~~~

We can name the individual calculation steps:

~~~java
// Phác thảo sau Extract Method:
CheckoutResult checkout(Order order) {
    long subtotal = calculateSubtotal(order);
    long discount = calculateDiscount(subtotal, order.vip);
    long payable = Math.subtractExact(subtotal, discount);
    long shipping = calculateShipping(payable);
    long total = Math.addExact(payable, shipping);
    String receipt = formatReceipt(subtotal, discount, shipping, total);
    return new CheckoutResult(
            subtotal, discount, shipping, total, receipt);
}
~~~

Methods such as calculateDiscount or calculateShipping can remain private with clear inputs and outputs. If a block reads or modifies too many local variables, determine which values it actually needs and returns rather than turning locals into shared fields accessible from everywhere.

Safe Extract Method procedure:

1. Run tests or establish existing input/output scenarios as a behavioral baseline.
2. Select a block with a distinct purpose; name it after **what it does**, not merely the technical operation.
3. Identify read variables, updated variables, return values, exceptions, and side effects.
4. Create the method, move the exact block, pass required dependencies as parameters, and replace the original code with a call.
5. Compile and rerun tests immediately after each small step.
6. Extract more only if intent becomes clearer; stop when extraction makes the flow harder to trace.

For example, **calculateShipping** expresses intent better than **processStep4**. Avoid passing a large object to use one field when a specific value makes the contract clearer; also avoid 10-parameter lists by choosing a parameter object that genuinely represents a concept.

## 4. Extract Class: Separate Responsibilities

After extracting methods, suppose CheckoutService has two groups:

- **Pricing:** Subtotals, VIP discounts, shipping fees, and totals.
- **Presentation:** Formatting receipts for display.

These groups change for different reasons. Move the first to **PricingPolicy**, the second to **ReceiptFormatter**, and retain **CheckoutService** as the coordinator.

~~~mermaid
flowchart TB
    subgraph BEFORE["Trước"]
        A["CheckoutService: kiểm tra + tính giá + định dạng"]
    end
    subgraph AFTER["Sau"]
        B["CheckoutService: điều phối"] --> C["PricingPolicy: quy tắc tiền"]
        B --> D["ReceiptFormatter: trình bày"]
    end
~~~

This applies the **Single Responsibility Principle (SRP)**: each class should have one coherent group of reasons to change. SRP does not mean exactly one method per class. Separation can also encourage abstraction-based dependencies when implementations need substitution, but not every class requires an interface.

## 5. Complete Java Program: Comparing Before and After Refactoring

Both versions preserve the same business requirements:

- An order has at least one line. SKU is nonblank, quantities are positive, and unit prices are nonnegative.
- **subtotal** is the sum of unit price multiplied by quantity; integer VND avoids floating-point inaccuracies.
- VIP customers with subtotals of at least **500.000 VND** get a **10% subtotal** discount, rounded down using integer division.
- Shipping is **0 VND** when the post-discount amount reaches **700.000 VND**; otherwise it is **30.000 VND**.
- **total = subtotal − discount + shipping**.
- Receipts use the fixed string format shown in the example.
- Calculations use Math.addExact, multiplyExact, and subtractExact so overflows do not silently alter results.

Save everything as **OrderRefactoringDemo.java**. This standalone **Java 11+** program has no external dependencies. LegacyCheckout combines business logic in one method; the refactored version separates PricingPolicy, ReceiptFormatter, and CheckoutService.

~~~java
import java.util.List;
import java.util.Objects;

public class OrderRefactoringDemo {
    static final long VIP_MIN_SUBTOTAL = 500_000L;
    static final long FREE_SHIPPING_MIN = 700_000L;
    static final long SHIPPING_FEE = 30_000L;

    static final class Item {
        final String sku;
        final long unitPriceVnd;
        final int quantity;

        Item(String sku, long unitPriceVnd, int quantity) {
            this.sku = sku;
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
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

    static final class CheckoutResult {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;
        final String receipt;

        CheckoutResult(long subtotal, long discount, long shipping,
                       long total, String receipt) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
            this.receipt = receipt;
        }
    }

    // TRƯỚC: một phương thức phải xử lý nhiều trách nhiệm.
    static final class LegacyCheckout {
        CheckoutResult checkout(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.unitPriceVnd < 0 || item.quantity <= 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineTotal = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineTotal);
            }

            long discount = order.vip && subtotal >= VIP_MIN_SUBTOTAL
                    ? subtotal / 10 : 0L;
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = payable >= FREE_SHIPPING_MIN
                    ? 0L : SHIPPING_FEE;
            long total = Math.addExact(payable, shipping);

            String receipt = "subtotal=" + subtotal
                    + ",discount=" + discount
                    + ",shipping=" + shipping
                    + ",total=" + total;

            return new CheckoutResult(
                    subtotal, discount, shipping, total, receipt);
        }
    }

    // KẾT QUẢ TÍNH TOÁN: dữ liệu cho lớp trình bày.
    static final class Pricing {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;

        Pricing(long subtotal, long discount, long shipping, long total) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
        }
    }

    // Extract Class: gom các quy tắc định giá liên quan.
    static final class PricingPolicy {
        Pricing calculate(Order order) {
            long subtotal = calculateSubtotal(order);
            long discount = calculateDiscount(subtotal, order.vip);
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = calculateShipping(payable);
            long total = Math.addExact(payable, shipping);

            return new Pricing(subtotal, discount, shipping, total);
        }

        // Extract Method: đọc và kiểm tra dữ liệu, rồi cộng tiền.
        private long calculateSubtotal(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.unitPriceVnd < 0 || item.quantity <= 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineTotal = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineTotal);
            }
            return subtotal;
        }

        private long calculateDiscount(long subtotal, boolean vip) {
            return vip && subtotal >= VIP_MIN_SUBTOTAL
                    ? subtotal / 10 : 0L;
        }

        private long calculateShipping(long payable) {
            return payable >= FREE_SHIPPING_MIN ? 0L : SHIPPING_FEE;
        }
    }

    // Extract Class: cách trình bày thay đổi độc lập với quy tắc giá.
    static final class ReceiptFormatter {
        String format(Pricing pricing) {
            return "subtotal=" + pricing.subtotal
                    + ",discount=" + pricing.discount
                    + ",shipping=" + pricing.shipping
                    + ",total=" + pricing.total;
        }
    }

    // SUT sau refactor: đọc như một quy trình điều phối.
    static final class CheckoutService {
        private final PricingPolicy pricingPolicy;
        private final ReceiptFormatter formatter;

        CheckoutService(PricingPolicy pricingPolicy,
                        ReceiptFormatter formatter) {
            this.pricingPolicy = Objects.requireNonNull(pricingPolicy);
            this.formatter = Objects.requireNonNull(formatter);
        }

        CheckoutResult checkout(Order order) {
            Pricing pricing = pricingPolicy.calculate(order);
            return new CheckoutResult(
                    pricing.subtotal,
                    pricing.discount,
                    pricing.shipping,
                    pricing.total,
                    formatter.format(pricing));
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void checkEquivalent(
            LegacyCheckout oldVersion,
            CheckoutService newVersion,
            Order input,
            long expectedTotal) {
        CheckoutResult oldResult = oldVersion.checkout(input);
        CheckoutResult newResult = newVersion.checkout(input);

        check(oldResult.subtotal == newResult.subtotal, "subtotal changed");
        check(oldResult.discount == newResult.discount, "discount changed");
        check(oldResult.shipping == newResult.shipping, "shipping changed");
        check(oldResult.total == newResult.total, "total changed");
        check(oldResult.receipt.equals(newResult.receipt),
                "receipt changed");
        check(newResult.total == expectedTotal, "incorrect total");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        LegacyCheckout oldVersion = new LegacyCheckout();
        CheckoutService newVersion =
                new CheckoutService(new PricingPolicy(),
                                    new ReceiptFormatter());

        // subtotal = 600.000; VIP giảm 60.000;
        // sau giảm 540.000; phí 30.000 => 570.000.
        Order vipOrder = new Order(List.of(
                new Item("BOOK", 250_000L, 2),
                new Item("PEN", 100_000L, 1)), true);
        checkEquivalent(oldVersion, newVersion, vipOrder, 570_000L);

        // Không VIP: 100.000 + phí 30.000 = 130.000.
        Order normalOrder = new Order(
                List.of(new Item("PEN", 100_000L, 1)), false);
        checkEquivalent(oldVersion, newVersion, normalOrder, 130_000L);

        // VIP: subtotal 800.000, giảm 80.000,
        // sau giảm 720.000, miễn phí vận chuyển.
        Order freeShippingOrder = new Order(
                List.of(new Item("BOOK", 400_000L, 2)), true);
        checkEquivalent(oldVersion, newVersion,
                freeShippingOrder, 720_000L);

        // Cả hai phiên bản từ chối quantity không hợp lệ.
        Order invalid = new Order(
                List.of(new Item("BOOK", 100_000L, 0)), false);
        expectInvalid(() -> oldVersion.checkout(invalid));
        expectInvalid(() -> newVersion.checkout(invalid));

        System.out.println("3 equivalent cases + invalid input: PASS");
    }
}
~~~

Compile and run:

~~~bash
javac OrderRefactoringDemo.java
java OrderRefactoringDemo
~~~

Expected output:

~~~text
3 equivalent cases + invalid input: PASS
~~~

This example **compares more than totals**: it checks subtotal, discount, shipping, total, and receipt strings, and verifies that both versions reject the same invalid input categories. For refactorings with side effects or external systems, add tests for observable effects at those boundaries.

**Example limitations:** The program models pure in-memory pricing without repositories, transactions, email delivery, or high volume. In real applications, test database state, meaningful side-effect ordering, thread safety, and integration failures before claiming behavior is preserved.

## 6. Identifying Responsibilities After Extraction

| Component | Current responsibility | Possible reason to change |
|---|---|---|
| Order / Item | Order and line-item data | Data contracts |
| PricingPolicy | Input validation and pricing, discounts, fees | Sales policies |
| Pricing | Calculated pricing result | Pricing data structure |
| ReceiptFormatter | Convert pricing results to a string | Display requirements |
| CheckoutService | Invoke PricingPolicy, then ReceiptFormatter | Coordinated business workflow |

Passing PricingPolicy and ReceiptFormatter through a constructor is simple **dependency injection**. Spring is not required. If multiple pricing/formatting variants are needed, consider matching interfaces; with just one implementation, concrete classes may be sufficient.

**When should a method stay in its original class?** When it uses most of that class's state and closely serves its core responsibility. Extract Class should move genuinely related behavior and data together rather than create a "Utils" class containing unrelated static methods.

## 7. Risks to Examine Before Declaring a Refactoring Successful

### Changing Execution Order or External Effects

Moving methods in the pure calculation example carries little risk. However, changing the order *charge payment → decrement inventory → log/send email* can alter business behavior. Refactorings involving transactions, locks, retries, or events must preserve promised invariants and transaction boundaries.

### Changing When Exceptions Are Thrown

Moving validation to another class may cause errors to surface earlier or later. For example, if the first line overflows and a later line is invalid, validating the entire cart up front changes the observable exception. Where exceptions or side effects are contractual, preserve ordering and write appropriate tests before moving logic.

### Exposing Data Internals

Do not make private fields public merely to let a new class access them. Use immutable value objects, meaningful query methods, or transfer state ownership to the responsible class.

### Introducing Circular Dependencies

It makes sense for CheckoutService to depend on PricingPolicy; if PricingPolicy must call back into CheckoutService, the responsibility split may be unclear. Favor one-way dependency direction rather than mutual references just to access helpers.

### Extracting Too Much

A class containing a single forwarding line is not necessarily valuable. Making every addition a class or method increases fragmentation. Extract according to business meaning, cohesion, and reasons to change—not to maximize file counts.

### Accidentally Changing Performance or Data Flow

Moving a method can introduce collection copies, caches with different lifetimes, or additional dependency calls. If performance, identity, ordering, concurrency, or idempotency are contractual, add corresponding checks. Watch Java reference semantics, mutable objects, and data races when moving state into shared classes.

## 8. Testing Before and After Refactoring

A practical sequence:

1. **Characterization tests:** Record existing behavior in important scenarios, especially where tests are missing.
2. **Small Extract Method steps:** Move one block and rerun the related tests.
3. **Responsibility-based Extract Class:** Move methods/fields and update dependencies in constructors and callers.
4. **Check equivalence:** Compare results, exceptions, state, and meaningful side effects.
5. **Run unit and integration tests:** Validate database, API, and transaction boundaries against real integrations where needed.
6. **Review diff scope:** Separate business-policy changes from refactoring to make regressions easier to detect.

When existing code has known defects, do not silently change behavior while claiming a "pure refactoring." Fix the bug separately with tests specifying the new expected behavior.

For example, if a pricing policy must change from a 10% discount to 15%, make that change **after** a behavior-preserving refactoring and test it separately. When a commit both extracts classes and changes rules, a failing test is harder to diagnose.

## 9. Practice Exercises

**Exercise 1 — Extract Method:** In LegacyCheckout, extract subtotal, discount, shipping-fee, and formatting calculations. Rerun the same tests after each step and explain each method's inputs and outputs.

**Exercise 2 — Extract Class:** Move the ReceiptFormatter responsibility separately and verify that changing output formatting does not require editing PricingPolicy. Explain how this improves cohesion.

**Exercise 3 — Boundary cases:** Add tests for VIP subtotals of exactly 500.000, payable amounts of exactly 700.000, empty orders, negative prices, quantities of 0, and values exceeding the long limit. Run both versions to check equivalence.

**Exercise 4 — Detect behavior changes:** Deliberately calculate shipping on the pre-discount subtotal instead of the post-discount payable amount. Construct an input where the results differ so a test catches the regression.

**Exercise 5 — Redesign:** If discount policies vary by country or customer type, consider a DiscountPolicy interface. Explain when Strategy is preferable to adding more if branches in PricingPolicy and when an interface would be premature.

## 10. Conclusion

**Extract Method** gives meaningful names to steps so the main method reads more clearly. **Extract Class** groups data and behavior by responsibility so components can evolve more independently. Both qualify as refactorings only when **the observable contract remains unchanged**. Make small, domain-named changes, verify before and after, and stop when the separation improves understanding.
