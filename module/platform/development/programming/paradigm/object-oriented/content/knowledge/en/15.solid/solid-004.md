# Liskov Substitution (LSP): Preserving Supertype Contracts

> Topic: OOP → SOLID → Liskov Substitution Principle. The focus is **behavioral substitutability**: a subtype object must work wherever a program expects its supertype while preserving the promises on which supertype clients rely.

## 1. What Does the Principle Say?

Suppose a function accepts an object of type `T`. If `S` is a subtype of `T`, passing an `S` object in place of `T` must preserve every property that the function is entitled to expect under `T`'s contract. In short:

~~~java
void process(T value) { /* chỉ dựa vào hợp đồng công khai của T */ }

// Nếu S <: T, process(new S(...)) vẫn phải đáp ứng hợp đồng của T.
~~~

LSP does not require subtypes to produce **identical concrete results**; each may use its own algorithm or policy. What matters is that every result and behavior stays within the supertype's promised contract.

Do not confuse "valid, compilable `extends` / `implements`" with "safe substitutability." The Java compiler enforces many type and method-override rules but cannot prove business contracts such as "discounts must not exceed the subtotal."

### What Does a Supertype Contract Include?

| Contract element | Supertype's promise | Subtype obligation |
|---|---|---|
| **Precondition** | Conditions a caller must satisfy before invoking a method, such as subtotal ≥ 0 | **Must not strengthen it:** Do not arbitrarily add new restrictions to valid inputs |
| **Postcondition** | Conditions that hold after a method completes, such as a discount in [0, subtotal] | **Must not weaken it:** Stronger guarantees are allowed, but all existing guarantees must remain |
| **Invariant** | State that must remain valid throughout the object's lifecycle | Never produce state that violates invariants relied upon by supertype clients |
| **Errors and exceptions** | How errors are reported for cases covered by the contract | Do not throw exceptions the contract disallows for valid inputs; Java's `checked exception` rules are only part of this |
| **Side effects/observable behavior** | Documented conventions for mutated data, call counts, order, or stability | Do not arbitrarily change promises on which clients are entitled to rely |

A method can define **invalid input** and throw corresponding errors. LSP does not require a subtype to accept every possible value; it must accept at least every input **valid under the supertype's contract**.

## 2. Practical Scenario: Calculating Checkout Discounts

Suppose a sales application offers multiple discount policies: fixed reductions and discounts for orders meeting a threshold. Checkout should not need to know each policy's type; it only needs the `DiscountPolicy` contract.

**Public contract:**

- The `subtotal` input must be non-`null` and ≥ 0. For `null` or negative values, throw `IllegalArgumentException`.
- For every valid `subtotal`, `discountFor(subtotal)` must return a `BigDecimal` that is not `null` and satisfies `0 ≤ discount ≤ subtotal`.
- Do not mutate the input or cause unexpected side effects; `BigDecimal` is already immutable here.
- A policy may choose its specific discount; it need not always apply a reduction or use the same amount.

### 2.1. LSP-Compliant Design (Java 17+)

Save the example as `LspDemo.java`; it compiles and runs with the JDK without external libraries.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

interface DiscountPolicy {
    /**
     * @param subtotal khác null và >= 0
     * @return giá trị khác null, nằm trong [0, subtotal]
     * @throws IllegalArgumentException nếu subtotal null hoặc âm
     */
    BigDecimal discountFor(BigDecimal subtotal);
}

final class Discounts {
    private Discounts() {}

    static void requireValid(BigDecimal subtotal) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
    }
}

/** Giảm một số tiền cố định, nhưng không bao giờ vượt tiền hàng. */
final class FixedDiscount implements DiscountPolicy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }
        this.amount = amount;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        return amount.min(subtotal);
    }
}

/** Đơn dưới ngưỡng được giảm 0, không phát sinh ngoại lệ. */
final class ThresholdDiscount implements DiscountPolicy {
    private static final BigDecimal THRESHOLD =
            new BigDecimal("100.00");
    private static final BigDecimal REWARD =
            new BigDecimal("10.00");

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        if (subtotal.compareTo(THRESHOLD) < 0) {
            return BigDecimal.ZERO;
        }
        return REWARD.min(subtotal);
    }
}

final class CheckoutService {
    BigDecimal total(BigDecimal subtotal, DiscountPolicy policy) {
        Discounts.requireValid(subtotal);
        BigDecimal discount =
                Objects.requireNonNull(policy, "policy")
                       .discountFor(subtotal);
        // Client được phép tin vào hợp đồng của DiscountPolicy.
        return subtotal.subtract(discount);
    }
}

public class LspDemo {
    public static void main(String[] args) {
        CheckoutService checkout = new CheckoutService();
        BigDecimal subtotal = new BigDecimal("25.00");

        List<DiscountPolicy> policies = List.of(
                new FixedDiscount(new BigDecimal("10.00")),
                new ThresholdDiscount()
        );
        for (DiscountPolicy policy : policies) {
            System.out.println(checkout.total(subtotal, policy));
        }
        // 15.00: chính sách giảm cố định
        // 25.00: chưa đạt ngưỡng nên giảm 0
    }
}
~~~

~~~bash
javac LspDemo.java
java LspDemo
~~~

**Why is substitution safe?** `CheckoutService.total` uses only `DiscountPolicy` and relies on discounts being nonnegative and no greater than the subtotal. Both implementations accept *every valid subtotal*, including 0 and very small orders. New policies can therefore be added without concrete-type branches in `CheckoutService`.

Viewed as a call flow:

~~~mermaid
flowchart TD
    C["CheckoutService.total(subtotal, policy)"]
    P["DiscountPolicy.discountFor(subtotal)"]
    F["FixedDiscount"]
    T["ThresholdDiscount"]
    R["Kiểm tra: 0 <= discount <= subtotal"]
    O["total = subtotal - discount"]
    C --> P
    P --> F
    P --> T
    F --> R
    T --> R
    R --> O
~~~

## 3. Two Common Ways to Violate LSP

### 3.1. Strengthening the Supertype's Precondition

~~~java
// Ví dụ SAI: chèn thêm class này vào cùng package với ví dụ trên.
final class BadVipDiscount implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        if (subtotal.compareTo(new BigDecimal("100")) < 0) {
            throw new UnsupportedOperationException(
                    "VIP discount only for orders >= 100");
        }
        return new BigDecimal("10.00");
    }
}
~~~

A subtotal of `25.00` is **valid input** under `DiscountPolicy`. Yet `BadVipDiscount` throws `UnsupportedOperationException`. This object cannot substitute for an arbitrary `DiscountPolicy` in `CheckoutService`, even though it compiles.

**Fix:** For orders below 100, return `BigDecimal.ZERO` as `ThresholdDiscount` does. If business rules require rejecting an order, define that behavior **in the supertype contract itself** or introduce a specialized abstraction; do not add hidden restrictions in a subclass.

### 3.2. Weakening a Postcondition

~~~java
// Ví dụ SAI: trả số tiền giảm cố định mà không chặn theo subtotal.
final class BadFixedDiscount implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        Discounts.requireValid(subtotal);
        return new BigDecimal("50.00");
    }
}
~~~

For an order of `25.00`, the discount returned is `50.00`, violating `discount ≤ subtotal`. `CheckoutService.total` then produces `-25.00`; a business error reaches the client even though it used the API correctly.

**Fix:** Return `new BigDecimal("50.00").min(subtotal)` as `FixedDiscount` does. For monetary calculations, prefer `BigDecimal(String)` to `new BigDecimal(double)` to avoid introducing binary floating-point inaccuracies.

| Case | `subtotal = 25.00` | Contract | Conclusion |
|---|---:|---|---|
| `FixedDiscount(10)` | Discount 10, resulting total 15 | Valid | Substitutable |
| `ThresholdDiscount` | Discount 0, resulting total 25 | Valid | Substitutable |
| `BadVipDiscount` | Throws `UnsupportedOperationException` | Invalid: adds a precondition | Violates LSP |
| `BadFixedDiscount` | Discount 50, resulting total negative | Invalid: violates a postcondition | Violates LSP |

These errors differ: **introducing a reason to reject valid input** strengthens a precondition; **returning a value outside the permitted range** weakens a postcondition. One implementation can violate several contract clauses at once.

## 4. Shared Contract Tests for Every Implementation

Separate unit tests for individual classes can miss substitutability problems. Instead, run **the same test suite** against every new `DiscountPolicy`. The following example uses JUnit Jupiter and JUnit 5 parameterized tests; `DiscountPolicyContractTest.java` should reside in the same package as the example classes, within the test source set.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.function.Supplier;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class DiscountPolicyContractTest {

    static Stream<Arguments> policies() {
        return Stream.of(
            Arguments.of("fixed",
                (Supplier<DiscountPolicy>) () ->
                    new FixedDiscount(new BigDecimal("10.00"))),
            Arguments.of("threshold",
                (Supplier<DiscountPolicy>) ThresholdDiscount::new)
        );
        // Thử bổ sung BadVipDiscount hoặc BadFixedDiscount vào đây:
        // bộ kiểm thử sẽ phát hiện hành vi phá hợp đồng.
    }

    @ParameterizedTest(name = "{0} respects valid inputs")
    @MethodSource("policies")
    void validSubtotalsReturnValidDiscount(
            String name, Supplier<DiscountPolicy> factory) {
        DiscountPolicy policy = factory.get();

        for (String input : new String[]{"0", "25.00", "100.00", "250.00"}) {
            BigDecimal subtotal = new BigDecimal(input);
            BigDecimal discount = assertDoesNotThrow(
                () -> policy.discountFor(subtotal),
                "A valid subtotal must not be rejected");

            assertNotNull(discount);
            assertTrue(discount.compareTo(BigDecimal.ZERO) >= 0);
            assertTrue(discount.compareTo(subtotal) <= 0);
        }
    }

    @ParameterizedTest(name = "{0} rejects invalid inputs as specified")
    @MethodSource("policies")
    void invalidSubtotalsFollowContract(
            String name, Supplier<DiscountPolicy> factory) {
        DiscountPolicy policy = factory.get();
        assertThrows(IllegalArgumentException.class,
            () -> policy.discountFor(null));
        assertThrows(IllegalArgumentException.class,
            () -> policy.discountFor(new BigDecimal("-1")));
    }
}
~~~

Note: Running this test requires JUnit Jupiter, JUnit Params, and test-runner configuration in Maven/Gradle. The goal is to **test observable behavior at the interface level**, not force every class to use the same formula. In the example, `BadVipDiscount` fails for `subtotal = 25`; `BadFixedDiscount` fails for `0` and `25`.

Testing a few values provides **limited evidence**, not mathematical proof for every input. For important monetary calculations, add boundary tests (0, exactly at thresholds, just below/above thresholds), very large values, high-precision decimal values, and property-based tests.

## 5. Classic OOP Example: Rectangle and Square

Suppose `Rectangle` exposes two independent setters, `setWidth(w)` and `setHeight(h)`, promising that each changes **only its corresponding dimension**. A `Square extends Rectangle` overrides `setWidth` to change the height as well, keeping both sides equal. This preserves the square's geometry but violates `Rectangle`'s promise that changing width does not affect height.

Example of a valid client of the supertype:

~~~java
void resize(Rectangle r) {
    r.setWidth(5);
    r.setHeight(4);
    // Theo hợp đồng setter độc lập: diện tích = 20.
    assert r.area() == 20;
}
~~~

If `Square` silently forces equal sides, the client no longer receives the behavior promised by the supertype. The problem lies in **the designed setter contract**, not in claiming that a square is not mathematically a rectangle.

Depending on requirements, a better design might use two immutable types implementing a common `Shape.area()` contract where the interface **makes no promise about independent setters**, or reuse behavior through composition instead of inheritance. Do not force a mathematical `is-a` relationship into `extends` when software contracts are incompatible.

## 6. How Does LSP Relate to the Other SOLID Principles?

- **SRP:** A class with clear responsibilities makes contracts easier to describe, but satisfying SRP does not guarantee LSP.
- **OCP:** When implementations honor contracts, a new `DiscountPolicy` can be added with minimal changes to `CheckoutService`; LSP is essential to safe extension.
- **ISP:** An overly broad interface may force implementations to `throw new UnsupportedOperationException()` for valid operations; capability-specific interfaces make contracts more honest.
- **DIP:** Clients depend on abstractions, but those abstractions only help if implementations follow the same behavioral contract.

LSP does not require class inheritance: using `implements` for an interface also creates a substitutability obligation. Conversely, a program without inheritance is not automatically "SOLID-compliant."

## 7. Applying LSP During Reviews or Refactoring

Before adding a subclass or implementation, answer these questions in order:

1. **Identify clients:** Which code accepts the supertype? What assumptions do clients rely on concerning parameters, results, errors, and side effects?
2. **Write the contract:** Specify valid inputs, exceptions for invalid inputs, valid outputs, invariants, and important behavior. Use JavaDoc, API documentation, and tests.
3. **Check the subtype:** Does it add input restrictions? Does it return `null`, throw unexpected exceptions, produce negative values or invalid states, mutate data, or introduce side effects for valid inputs?
4. **Run contract tests:** Apply the same interface-level test suite to every implementation. Add risk-based boundary and integration tests.
5. **Redesign incompatible contracts:** Split interfaces by capability, make "unsupported" an explicitly defined outcome, or use composition. Do not hide the problem with client-side `instanceof` branches for subtypes.

### Common Mistakes

- Checking only `@Override`, method signatures, or checked-exception restrictions and declaring the design "LSP-compliant."
- Writing subtype methods that throw `UnsupportedOperationException` even when the abstraction promises that operation.
- Allowing a subtype to return `null` when the supertype promises non-`null` results, or values outside the valid range.
- Using `instanceof BadVipDiscount` inside `CheckoutService` to compensate for a broken contract: this moves subtype knowledge into the client and increases branching as the system grows.
- Assuming every subtype must have identical results, performance, or algorithmic details: only contractually promised properties are required. If latency, processing order, idempotency, or thread safety are public guarantees, they must also be preserved.

**Key takeaway:** Syntactically valid inheritance is not enough. Ask: "If a caller knows only the supertype, can it safely accept this subtype?" If not, fix the implementation or redesign the contract and type relationships.
