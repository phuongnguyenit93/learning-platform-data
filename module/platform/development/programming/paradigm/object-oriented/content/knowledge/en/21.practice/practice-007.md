# Hands-on exercise: Refactoring procedural code into an object model (Java)

**Topic:** OOP → Practice → Refactoring procedural code into an object model  
**Level:** Intermediate | **Requirements:** Java 17 or later, JDK, terminal; no external libraries.

## 1. Context and requirements

A sales application calculates order totals in a function. Its initial procedural version combines input data, customer-type checks, discounts, and shipping fees in one function. Changes to policies or reuse of individual rules make the function difficult to test and error-prone.

**Business rules to preserve for valid input:**

1. Subtotal = unit price × quantity; all monetary amounts are whole-number VND.
2. VIP customers receive a **10% subtotal discount**, rounded down to whole VND using integer division; REGULAR customers have no discount.
3. Shipping is free when the post-discount amount is **1.000.000 VND or more**.
4. Below the free-shipping threshold: NORMAL = 20.000 VND, EXPRESS = 50.000 VND.
5. Total payable = subtotal − discount + shipping fee.

**Expected outcome:** Reorganize the model into objects with clear responsibilities, hide internal state, replace classification strings with type-safe values, separate discount policies from checkout flow, and prove that calculated totals remain unchanged.

## 2. Starting procedural implementation

Assume all inputs are valid and the following initial logic must be preserved:

~~~java
public static long calculateTotal(
        String customerType, long unitPriceVnd,
        int quantity, String shippingMode) {

    long subtotal = Math.multiplyExact(unitPriceVnd, quantity);

    long discount = "VIP".equals(customerType)
            ? subtotal / 10 : 0;

    long afterDiscount = subtotal - discount;

    long shippingFee;
    if (afterDiscount >= 1_000_000L) {
        shippingFee = 0L;
    } else if ("EXPRESS".equals(shippingMode)) {
        shippingFee = 50_000L;
    } else {
        shippingFee = 20_000L;
    }

    return Math.addExact(afterDiscount, shippingFee);
}
~~~

**Design observations beyond syntax:**

- One function handles input, customer types, pricing, and shipping decisions; many independent reasons could cause it to change.
- String values are easy to mistype: for example, "vip" is treated as REGULAR and "EXPREES" as NORMAL without an error.
- Discount policy is hardcoded into the function, so a new customer type requires changes to orchestration.
- The result contains only a total; an invoice view cannot show discounts or shipping fees separately.
- There is no clear boundary for invalid data (negative unit prices, quantity 0).

**Note:** This exercise improves design and adds validation. Rejecting invalid inputs intentionally changes behavior; only results for valid inputs are required to remain unchanged.

## 3. Implementation tasks

Work through these steps before viewing the solution:

1. **Encapsulate data:** create an Order class that holds unit price, quantity, customer type, and shipping mode; disallow arbitrary modification after construction. Move subtotal calculation into Order.
2. **Replace magic strings:** use enum CustomerType { REGULAR, VIP } and ShippingMode { NORMAL, EXPRESS }.
3. **Extract policy:** define DiscountPolicy and two implementations, NoDiscount and VipDiscount. Each policy returns only the discount, without calculating shipping fees.
4. **Extract service:** ShippingPolicy calculates shipping from the discounted amount and shipping mode; CheckoutService coordinates objects and returns a Receipt with each amount.
5. **Regression tests:** compare REGULAR/VIP, NORMAL/EXPRESS, free/non-free shipping, and cases near the 1.000.000 VND threshold.
6. **Validate errors:** reject negative prices, nonpositive quantities, and null required objects; reject discount policies returning negative values or values greater than subtotal.

Do not introduce objects merely to rename functions. Ask what data/rules each object owns, who can modify them, and which tests confirm that responsibility.

## 4. Assigning OOP responsibilities

| Component | Primary responsibility | Avoid |
|---|---|---|
| Order | Hold valid order data and calculate subtotal | Calculating discounts or printing invoices |
| CustomerType, ShippingMode | Represent valid business choices | Passing arbitrary strings throughout the system |
| DiscountPolicy | Contract for calculating discounts from subtotal | Depending directly on shipping |
| NoDiscount, VipDiscount | Implement two discount rules | Reintroducing customer-type if-else branches inside each policy |
| ShippingPolicy | Calculate fees from post-discount amounts and shipping mode | Recalculating subtotal or discounts |
| CheckoutService | Orchestrate, enforce invariants, and create Receipt | Containing every policy implementation |
| Receipt | Observable and testable calculation result | Silently changing amounts during display |

~~~mermaid
classDiagram
    class Order {
      -CustomerType customerType
      -ShippingMode shippingMode
      -long unitPriceVnd
      -int quantity
      +subtotalVnd() long
    }
    class DiscountPolicy {
      <<interface>>
      +discountVnd(long) long
    }
    class NoDiscount
    class VipDiscount
    class ShippingPolicy {
      +feeVnd(long, ShippingMode) long
    }
    class CheckoutService {
      +checkout(Order) Receipt
    }
    class Receipt
    DiscountPolicy <|.. NoDiscount
    DiscountPolicy <|.. VipDiscount
    CheckoutService --> Order
    CheckoutService --> DiscountPolicy
    CheckoutService --> ShippingPolicy
    CheckoutService --> Receipt
~~~

**Design intent:** Order protects its state and provides data-related behavior; DiscountPolicy uses **polymorphism** to choose discount algorithms; CheckoutService uses **composition** to coordinate them. ShippingPolicy currently has only one calculation approach, so no separate interface is needed.

## 5. Complete standalone reference solution

Create a **RefactorCheckout.java** file and paste in all the code below. Nested classes keep this demonstration in one runnable file; in a real project they can be split into files within the same package.

~~~java
import java.util.Map;
import java.util.Objects;

public class RefactorCheckout {

    enum CustomerType { REGULAR, VIP }
    enum ShippingMode { NORMAL, EXPRESS }

    static final class Order {
        private final CustomerType customerType;
        private final ShippingMode shippingMode;
        private final long unitPriceVnd;
        private final int quantity;

        Order(CustomerType customerType, ShippingMode shippingMode,
              long unitPriceVnd, int quantity) {
            this.customerType =
                    Objects.requireNonNull(customerType, "customerType");
            this.shippingMode =
                    Objects.requireNonNull(shippingMode, "shippingMode");
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException("Unit price must be >= 0");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Quantity must be > 0");
            }
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
        }

        CustomerType customerType() {
            return customerType;
        }

        ShippingMode shippingMode() {
            return shippingMode;
        }

        long subtotalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    interface DiscountPolicy {
        long discountVnd(long subtotalVnd);
    }

    static final class NoDiscount implements DiscountPolicy {
        @Override
        public long discountVnd(long subtotalVnd) {
            return 0L;
        }
    }

    static final class VipDiscount implements DiscountPolicy {
        @Override
        public long discountVnd(long subtotalVnd) {
            return subtotalVnd / 10L;  // 10%, làm tròn xuống 1 VND
        }
    }

    static final class ShippingPolicy {
        long feeVnd(long afterDiscountVnd, ShippingMode mode) {
            Objects.requireNonNull(mode, "mode");
            if (afterDiscountVnd >= 1_000_000L) {
                return 0L;
            }
            return mode == ShippingMode.EXPRESS ? 50_000L : 20_000L;
        }
    }

    record Receipt(long subtotalVnd, long discountVnd,
                   long shippingVnd, long totalVnd) { }

    static final class CheckoutService {
        private final Map<CustomerType, DiscountPolicy> discountPolicies;
        private final ShippingPolicy shippingPolicy;

        CheckoutService(
                Map<CustomerType, DiscountPolicy> discountPolicies,
                ShippingPolicy shippingPolicy) {
            this.discountPolicies =
                    Map.copyOf(Objects.requireNonNull(discountPolicies));
            this.shippingPolicy =
                    Objects.requireNonNull(shippingPolicy);
        }

        Receipt checkout(Order order) {
            Objects.requireNonNull(order, "order");

            long subtotal = order.subtotalVnd();
            DiscountPolicy policy =
                    discountPolicies.get(order.customerType());

            if (policy == null) {
                throw new IllegalStateException(
                        "Missing policy for " + order.customerType());
            }

            long discount = policy.discountVnd(subtotal);
            if (discount < 0 || discount > subtotal) {
                throw new IllegalStateException("Invalid discount");
            }

            long afterDiscount = Math.subtractExact(subtotal, discount);
            long shipping =
                    shippingPolicy.feeVnd(afterDiscount, order.shippingMode());
            if (shipping < 0) {
                throw new IllegalStateException("Invalid shipping fee");
            }

            long total = Math.addExact(afterDiscount, shipping);
            return new Receipt(subtotal, discount, shipping, total);
        }
    }

    private static void expectTotal(
            CheckoutService checkout, Order order, long expected) {
        Receipt receipt = checkout.checkout(order);
        if (receipt.totalVnd() != expected) {
            throw new AssertionError(
                    "Expected " + expected + ", actual " + receipt);
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Đầu vào sai đã bị từ chối đúng dự kiến.
        }
    }

    public static void main(String[] args) {
        CheckoutService checkout = new CheckoutService(
                Map.of(
                        CustomerType.REGULAR, new NoDiscount(),
                        CustomerType.VIP, new VipDiscount()),
                new ShippingPolicy());

        // VIP: 1.200.000 - 120.000 = 1.080.000, miễn phí giao.
        expectTotal(checkout,
                new Order(CustomerType.VIP, ShippingMode.EXPRESS,
                        400_000L, 3),
                1_080_000L);

        // REGULAR: 400.000 + 20.000 phí giao thường.
        expectTotal(checkout,
                new Order(CustomerType.REGULAR, ShippingMode.NORMAL,
                        400_000L, 1),
                420_000L);

        // VIP: 400.000 - 40.000 + 50.000 giao nhanh.
        expectTotal(checkout,
                new Order(CustomerType.VIP, ShippingMode.EXPRESS,
                        400_000L, 1),
                410_000L);

        // Tính ngưỡng miễn phí theo giá SAU giảm: 990.000 < 1.000.000.
        expectTotal(checkout,
                new Order(CustomerType.VIP, ShippingMode.NORMAL,
                        1_100_000L, 1),
                1_010_000L);

        // Đúng ngưỡng: 1.000.000, giao thường miễn phí.
        expectTotal(checkout,
                new Order(CustomerType.REGULAR, ShippingMode.NORMAL,
                        1_000_000L, 1),
                1_000_000L);

        expectInvalid(() -> new Order(
                CustomerType.REGULAR, ShippingMode.NORMAL, -1L, 1));
        expectInvalid(() -> new Order(
                CustomerType.VIP, ShippingMode.EXPRESS, 10_000L, 0));

        Receipt receipt = checkout.checkout(
                new Order(CustomerType.VIP, ShippingMode.EXPRESS,
                        400_000L, 1));
        System.out.println(receipt);
        System.out.println("PASS: 5 business cases + 2 invalid inputs");
    }
}
~~~

Run with:

~~~bash
javac RefactorCheckout.java
java RefactorCheckout
~~~

Sample output:

~~~text
Receipt[subtotalVnd=400000, discountVnd=40000, shippingVnd=50000, totalVnd=410000]
PASS: 5 business cases + 2 invalid inputs
~~~

In a production program, policies can live in separate classes. A configuration map is supplied through the constructor, so CheckoutService need not know the concrete implementation for each customer type. If another customer type is introduced, register its policy at the configuration point after updating the enum; the checkout algorithm needs no modification.

## 6. Required test cases

| Customer | Unit price × Qty | Shipping | Discount | Shipping fee | Expected total |
|---|---:|---|---:|---:|---:|
| REGULAR | 400.000 × 1 | NORMAL | 0 | 20.000 | **420.000** |
| VIP | 400.000 × 1 | EXPRESS | 40.000 | 50.000 | **410.000** |
| VIP | 400.000 × 3 | EXPRESS | 120.000 | 0 | **1.080.000** |
| VIP | 1.100.000 × 1 | NORMAL | 110.000 | 20.000 | **1.010.000** |
| REGULAR | 1.000.000 × 1 | NORMAL | 0 | 0 | **1.000.000** |

Add a comparison table of **before/after refactoring results** for every valid input; totals must match. Testing the free-shipping threshold is especially important: if subtotal 1.100.000 is mistakenly checked before the discount, the VIP case in the fourth row incorrectly receives free shipping.

**Include error tests for:** null CustomerType/ShippingMode, quantity 0 or negative, negative price, missing DiscountPolicy for a customer type, discount policies returning negative or above-subtotal values, and long multiplication/addition overflow. The example uses Math.multiplyExact/Math.addExact to throw ArithmeticException instead of silently returning an incorrect result. Avoid double for whole VND amounts; consider BigDecimal with explicit rounding rules for fractional or multicurrency payments.

## 7. Refactoring safely in a real codebase

~~~mermaid
flowchart TD
    A[Chốt đầu vào và luật hiện hữu] --> B[Viết characterization tests]
    B --> C[Đưa dữ liệu vào Order]
    C --> D[Thay chuỗi phân loại bằng enum]
    D --> E[Tách DiscountPolicy và ShippingPolicy]
    E --> F[Đưa luồng điều phối vào CheckoutService]
    F --> G[So sánh đầu ra trước và sau]
    G --> H{Các ca đều khớp?}
    H -- Không --> I[Định vị khác biệt và sửa]
    I --> G
    H -- Có --> J[Xóa đường xử lý cũ, giữ test]
~~~

Make one verifiable change at a time: **Extract Class → Encapsulate Field → Extract Method → Introduce Strategy → Move Method**. Run tests after each step. If legacy code accepts negative prices or arbitrary customer strings, document tighter validation as a separate business-rule change and test it explicitly; do not confuse refactoring regressions with intended behavior changes.

### Signs of a successful refactor

- Each class has a purpose explainable in one sentence; Order fields are private final.
- Adding a discount formula mainly involves implementing DiscountPolicy and registering it in configuration.
- Comparisons against "VIP" or "EXPRESS" are not scattered through CheckoutService.
- Callers cannot directly modify unit price, quantity, or shipping mode after constructing Order.
- Receipt exposes subtotal, discount, shipping fee, and total for invoices and tests.
- Tests verify business results, not just class names or getters.

### Common design mistakes

- **God object:** move the entire old function into Order and make it handle discounts, shipping, and invoice printing.
- **Extreme anemic model:** leave Order with only public getters/setters and move all data-related behavior into static utilities.
- **Superficial polymorphism:** create interfaces for every class even when only one stable policy exists; introduce abstractions at actual variation points.
- **Using double for money:** floating-point representation may be inaccurate; this exercise uses long VND.
- **Testing only the happy path:** overlook shipping thresholds and invalid inputs.
- **Unintended behavior changes:** apply the threshold to subtotal instead of post-discount amount, or round the 10% differently from the original.

## 8. Extensions and submission criteria

**Exercise A — Bronze:** Replace customer/shipping type strings; extract Order, CheckoutService, and Receipt; retain all 5 table results.

**Exercise B — Silver:** Complete DiscountPolicy, test CheckoutService with a fake policy returning an arbitrary discount, and reject invalid discount values.

**Exercise C — Gold:** Add a PREMIUM = 15% discount policy to the enum and configuration without changing CheckoutService.checkout. Test that free shipping is checked using the post-discount price. Document and test any changes to rounding rules for fractional results.

**Submission:** Runnable Java 17+ code, a before/after test-case table with matching results, a class diagram or responsibility table, and a brief explanation of encapsulation, composition, and polymorphism. The exercise is complete once the legacy logic is safely replaced, duplication is removed, and all regression cases pass.
