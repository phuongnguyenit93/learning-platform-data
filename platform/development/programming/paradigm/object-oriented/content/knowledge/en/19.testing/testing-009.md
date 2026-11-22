# Regression Testing When OOP Designs Change

## 1. The Problem: Changing Code Structure While Preserving Behavior

In OOP, a design might evolve from one large class to several smaller classes, extract interfaces, adopt **Strategy**, add **Dependency Injection (DI)**, or change object collaboration. Such changes are often **refactoring**: improving internal structure without intending to change external behavior.

**Regression testing** reruns existing tests and adds necessary cases to detect broken behavior after a change. The core question is:

> After changing the design, do the same valid inputs and states still produce the results, failures, and side effects promised by the contract?

For example, an initial implementation may calculate order totals in one method. After refactoring, it uses Strategy to calculate shipping. Clients must still receive the correct invoice; an order exactly at the free-shipping threshold must ship free; invalid data must still be rejected as contracted.

**Learning outcomes:**

- Identify **observable behavior** that must remain stable when changing a design.
- Write requirement-based regression tests with explicit inputs and expected outputs.
- Run the same suite against **old and new designs** through a shared interface.
- Detect boundary, exception, state, and object-interaction defects.
- Distinguish **comparing two versions** from an **independent source of truth** in the business contract.
- Establish regression-testing practices in reviews/CI before and after refactoring.

## 2. What Must Remain Unchanged?

Suppose an order-quoting system has these requirements:

1. `subtotalCents` is an integer number of cents between **0 and 1.000.000**, inclusive.
2. Members always receive **free shipping**.
3. Nonmembers with `subtotalCents >= 100_000` get free shipping; below the threshold, shipping costs **15.000 cents**.
4. `totalCents = subtotalCents + shippingCents`.
5. An out-of-range merchandise subtotal throws `IllegalArgumentException`.
6. Quoting does not mutate the order or system data.

Class organization is an implementation detail. **The returned `Invoice`, failures, and side effects** are what clients legitimately expect.

| Element | May Change During Refactoring | Must Remain Contractually Stable |
|---|---|---|
| Class design | Split `Checkout` and `ShippingRule`, rename internal classes | Clients can still invoke the published quoting service |
| Internal algorithm | Extract conditions, replace with Strategy | Pricing and shipping rules remain the same |
| Dependencies | Introduce constructor injection | Valid inputs still succeed |
| Return value | Object construction process | Monetary fields in `Invoice` are correct |
| Exceptions | Where validation occurs | Out-of-domain inputs are rejected as promised |
| State/side effects | Storage or component collaboration | No unexpected data writes occur |
| Performance | Cache or algorithm optimization | Any contractual SLA remains satisfied |

**Note:** Not every detail must remain unchanged. If business requirements deliberately change, affected tests should be updated intentionally and reviewed; this is no longer pure refactoring.

## 3. Three Types of Evidence for Regression Tests

A good suite does more than compare `before` and `after`:

- **Specification examples:** cases with expected outcomes derived from business requirements. These provide independent oracles to avoid copying preexisting defects.
- **Differential testing:** run the same inputs against old and new versions and compare observable outcomes. This detects differences beyond a fixed example set.
- **Invariant/contract tests:** verify persistent properties such as `total = subtotal + shipping`, nonnegative totals, and consistent input-error behavior.

No single approach gives absolute assurance. If old code is wrong, both versions can return the same wrong result and still pass a `before/after` comparison. Prefer **validated contracts** as the correctness oracle.

## 4. Runnable Java Example: Refactoring Checkout to Strategy

Use **JDK 17 or newer**. Create one file, `DesignRegressionDemo.java`, paste the complete code below, and run it without external libraries:

~~~java
import java.util.Random;

public final class DesignRegressionDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;
    private static final long FREE_SHIPPING_AT = 100_000L;
    private static final long STANDARD_SHIPPING = 15_000L;

    // Hợp đồng chung mà các client sử dụng.
    interface PriceQuoteService {
        Invoice quote(long subtotalCents, boolean member);
    }

    // Value object bất biến, equals() so sánh theo giá trị.
    record Invoice(long shippingCents, long totalCents) {}

    private static void validateSubtotal(long subtotalCents) {
        if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
            throw new IllegalArgumentException("subtotalCents out of range");
        }
    }

    // BEFORE: nghiệp vụ và logic vận chuyển trong một class.
    static final class LegacyCheckout implements PriceQuoteService {
        @Override
        public Invoice quote(long subtotalCents, boolean member) {
            validateSubtotal(subtotalCents);
            long shipping = (member || subtotalCents >= FREE_SHIPPING_AT)
                    ? 0L : STANDARD_SHIPPING;
            return new Invoice(shipping, subtotalCents + shipping);
        }
    }

    // AFTER: tách chính sách giao hàng ra khỏi Checkout.
    interface ShippingRule {
        long shippingFor(long subtotalCents, boolean member);
    }

    static final class StandardShippingRule implements ShippingRule {
        @Override
        public long shippingFor(long subtotalCents, boolean member) {
            if (member || subtotalCents >= FREE_SHIPPING_AT) {
                return 0L;
            }
            return STANDARD_SHIPPING;
        }
    }

    static final class RefactoredCheckout implements PriceQuoteService {
        private final ShippingRule shippingRule;

        RefactoredCheckout(ShippingRule shippingRule) {
            this.shippingRule = java.util.Objects.requireNonNull(shippingRule);
        }

        @Override
        public Invoice quote(long subtotalCents, boolean member) {
            validateSubtotal(subtotalCents);
            long shipping = shippingRule.shippingFor(subtotalCents, member);
            return new Invoice(shipping, subtotalCents + shipping);
        }
    }

    // AFTER nhưng cố ý LỖI: > thay vì >= ở ngưỡng miễn phí.
    static final class BrokenShippingRule implements ShippingRule {
        @Override
        public long shippingFor(long subtotalCents, boolean member) {
            if (member || subtotalCents > FREE_SHIPPING_AT) {
                return 0L;
            }
            return STANDARD_SHIPPING;
        }
    }

    // Expected value đến từ đặc tả, không gọi production code để tự tính.
    record Example(long subtotal, boolean member, Invoice expected) {}

    private static final Example[] EXAMPLES = {
        new Example(0L,       false, new Invoice(15_000L,   15_000L)),
        new Example(0L,       true,  new Invoice(0L,             0L)),
        new Example(99_999L,  false, new Invoice(15_000L,  114_999L)),
        new Example(100_000L, false, new Invoice(0L,       100_000L)),
        new Example(100_001L, false, new Invoice(0L,       100_001L)),
        new Example(99_999L,  true,  new Invoice(0L,        99_999L)),
        new Example(1_000_000L, false, new Invoice(0L,   1_000_000L))
    };

    private static void require(boolean condition, String detail) {
        if (!condition) {
            throw new AssertionError(detail);
        }
    }

    // Chạy được cho mọi implementation của PriceQuoteService.
    static void verifyAgainstSpecification(
            String label, PriceQuoteService service) {
        for (Example example : EXAMPLES) {
            Invoice actual = service.quote(example.subtotal(), example.member());

            require(actual.equals(example.expected()),
                label + ": wrong quote at subtotal=" + example.subtotal()
                + ", member=" + example.member()
                + ", expected=" + example.expected()
                + ", actual=" + actual);

            require(actual.shippingCents() >= 0L,
                label + ": shipping cannot be negative");
            require(actual.totalCents()
                    == example.subtotal() + actual.shippingCents(),
                label + ": total must equal subtotal + shipping");
        }

        expectInvalid(label, service, -1L);
        expectInvalid(label, service, MAX_SUBTOTAL + 1L);
    }

    private static void expectInvalid(
            String label, PriceQuoteService service, long subtotal) {
        try {
            service.quote(subtotal, false);
            throw new AssertionError(label + ": accepted invalid subtotal " + subtotal);
        } catch (IllegalArgumentException expected) {
            // Đúng hợp đồng: từ chối input không hợp lệ.
        }
    }

    // So sánh hai thiết kế trên nhiều input có thể tái lập.
    static void verifySameBehavior(
            PriceQuoteService before, PriceQuoteService after) {
        Random random = new Random(209L);
        for (int i = 0; i < 1_000; i++) {
            long subtotal = random.nextInt(1_000_001);
            boolean member = random.nextBoolean();

            Invoice expectedFromOld = before.quote(subtotal, member);
            Invoice actualFromNew = after.quote(subtotal, member);
            require(expectedFromOld.equals(actualFromNew),
                "Behavior changed at subtotal=" + subtotal
                + ", member=" + member);
        }
    }

    public static void main(String[] args) {
        PriceQuoteService before = new LegacyCheckout();
        PriceQuoteService after =
            new RefactoredCheckout(new StandardShippingRule());

        verifyAgainstSpecification("LegacyCheckout", before);
        System.out.println("PASS specification: LegacyCheckout");

        verifyAgainstSpecification("RefactoredCheckout", after);
        System.out.println("PASS specification: RefactoredCheckout");

        verifySameBehavior(before, after);
        System.out.println("PASS differential: before vs after");

        // Minh họa khả năng phát hiện regression ở đúng điểm biên.
        PriceQuoteService broken =
            new RefactoredCheckout(new BrokenShippingRule());
        boolean regressionDetected = false;
        try {
            verifyAgainstSpecification("BrokenShippingRule", broken);
        } catch (AssertionError error) {
            regressionDetected = true;
            System.out.println("EXPECTED FAIL: " + error.getMessage());
        }
        require(regressionDetected, "The broken implementation was not detected");
        System.out.println("DONE: regression tests caught the design-change bug");
    }
}
~~~

Run from a terminal:

~~~bash
javac DesignRegressionDemo.java
java DesignRegressionDemo
~~~

Expected output (lines may be longer depending on the record's `toString()`):

~~~text
PASS specification: LegacyCheckout
PASS specification: RefactoredCheckout
PASS differential: before vs after
EXPECTED FAIL: BrokenShippingRule: wrong quote at subtotal=100000, member=false, ...
DONE: regression tests caught the design-change bug
~~~

**Defect explanation:** `BrokenShippingRule` uses `subtotalCents > 100_000`. When the subtotal is **exactly** 100.000 for a nonmember, it charges 15.000 even though the contract requires free shipping. This is an **off-by-one boundary defect**. Both the old and new classes implement `PriceQuoteService`, but only the correctly refactored design preserves behavior.

In this example, `main` catches `AssertionError` from an **intentionally broken** implementation for demonstration. In actual regression suites, the CI job must **FAIL**; do not convert errors into passing results.

## 5. Why Is This More Reliable Than Testing Internals?

Consider the class relationships after refactoring:

~~~mermaid
classDiagram
    class PriceQuoteService {
      <<interface>>
      +quote(long, boolean) Invoice
    }
    class LegacyCheckout
    class RefactoredCheckout
    class ShippingRule {
      <<interface>>
      +shippingFor(long, boolean) long
    }
    class StandardShippingRule
    class BrokenShippingRule
    PriceQuoteService <|.. LegacyCheckout
    PriceQuoteService <|.. RefactoredCheckout
    RefactoredCheckout --> ShippingRule : sử dụng
    ShippingRule <|.. StandardShippingRule
    ShippingRule <|.. BrokenShippingRule
~~~

The suite invokes `quote()` through **`PriceQuoteService`**, observes the returned `Invoice` and public exceptions, and therefore remains meaningful when an internal `if` becomes a constructor-injected Strategy.

**Do not** require a particular class to invoke `shippingRule.shippingFor()` exactly once, or to contain a specific `private` method, in a regression test. These design details may change while results stay correct. Assert call counts or interaction order only when **actually promised**, such as never charging a card twice.

## 6. Build a Regression Matrix Before Refactoring

| Test Category | Example Case | Typical Defect Detected |
|---|---|---|
| Normal cases | Member/nonmember, small/large orders | Branch logic changes during extraction |
| Boundary values | 0; 99.999; **100.000**; 100.001; 1.000.000 | `>`/`>=`, incorrect shipping fees, overflow |
| Invalid inputs | -1; 1.000.001 | Missing validation or changed error type |
| Output contract | Total = subtotal + shipping | Inconsistent results across components |
| State | Repeated calls; data before and after | State changes during responsibility extraction |
| Side effects | Quoting does not write to DB or charge money | Refactor inadvertently invokes a side-effectful command |
| Integration | API → service → simulated repository/payment gateway | Incorrect wiring/DI or transaction behavior |
| Contention | Concurrent requests against a shared object | Cache or shared mutable state creates races |
| Nonfunctional | Response time within a promised threshold | Unexpected query/I/O increases |

**Select cases based on risk.** For changes mainly within pure Java domain logic, prioritize unit, contract, and boundary tests. For wiring, transaction, data, or serialization changes, add integration tests. For API surface changes, include payload contract or backward-compatibility tests.

## 7. Applying JUnit 5 in a Real Project

In a Maven/Gradle project with **JUnit Jupiter** configured and `DesignRegressionDemo` in the same package as tests, move checks into `@Test`/`@TestFactory`. Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CheckoutRegressionTest {
    @Test
    void minimumFreeShippingBoundaryMustRemainUnchanged() {
        DesignRegressionDemo.PriceQuoteService service =
            new DesignRegressionDemo.RefactoredCheckout(
                new DesignRegressionDemo.StandardShippingRule());

        assertEquals(
            new DesignRegressionDemo.Invoice(0, 100_000),
            service.quote(100_000, false)
        );
    }

    @Test
    void rejectsOutOfRangeSubtotals() {
        DesignRegressionDemo.PriceQuoteService service =
            new DesignRegressionDemo.RefactoredCheckout(
                new DesignRegressionDemo.StandardShippingRule());

        assertThrows(IllegalArgumentException.class,
            () -> service.quote(-1, false));
        assertThrows(IllegalArgumentException.class,
            () -> service.quote(1_000_001, false));
    }

    @Test
    void refactoringKeepsContractAndSampledBehavior() {
        DesignRegressionDemo.PriceQuoteService before =
            new DesignRegressionDemo.LegacyCheckout();
        DesignRegressionDemo.PriceQuoteService after =
            new DesignRegressionDemo.RefactoredCheckout(
                new DesignRegressionDemo.StandardShippingRule());

        DesignRegressionDemo.verifyAgainstSpecification("old", before);
        DesignRegressionDemo.verifyAgainstSpecification("new", after);
        DesignRegressionDemo.verifySameBehavior(before, after);
    }
}
~~~

Put tests in `src/test/java` under the same package to access non-`public` nested types from this example. Production applications usually split types into files and choose access modifiers appropriate to the public API.

When moving to JUnit, **do not put an intentionally broken implementation among tests expected to PASS**. To demonstrate that tests detect the sample defect, use mutation testing or a separate controlled example. Genuine production failures must remain failures that block the pipeline.

## 8. Implementing Regression Tests Step by Step

1. **Establish the current contract.** Document requirements, examples, boundaries, allowed errors, invariants, and side effects. Review ambiguities with a domain expert.
2. **Create a baseline before changing the design.** Run tests on current code; record passes, failures, and known defects. Do not assume old behavior is automatically correct.
3. **Add boundary and critical-flow cases.** Prioritize code areas most likely to change behavior.
4. **Refactor in small increments.** Extract abstractions, move dependencies, or change object construction, rerunning tests after each change.
5. **Compare both contracts and versions.** Use independent example-based tests first, then differential tests over a wider input range.
6. **Run the right test layers.** Unit tests catch logic defects; integration tests verify wiring, transactions, and side effects; end-to-end tests check main user workflows.
7. **Integrate with CI and review.** Run automated test jobs reporting failing cases/inputs; never hide failures by arbitrarily modifying expected values.
8. **Remove the old design deliberately.** Once the refactor is stable and verified, retire old paths; retain **specification tests** as a long-term regression suite. Differential tests tied solely to old code may be retired when comparison is no longer needed.

~~~mermaid
flowchart TD
    A["Chốt hợp đồng và baseline"] --> B["Viết test đặc tả + biên"]
    B --> C["Refactor từng bước nhỏ"]
    C --> D["Chạy unit/contract regression tests"]
    D --> E{"Các cam kết còn đúng?"}
    E -->|Không| F["Điều tra lỗi, sửa code hoặc làm rõ yêu cầu"]
    F --> D
    E -->|Có| G["Chạy integration + luồng quan trọng"]
    G --> H{"Đã xác minh thay đổi?"}
    H -->|Chưa| F
    H -->|Rồi| I["Merge và giữ regression suite trong CI"]
~~~

## 9. Mistakes to Avoid

**Running only the new class's tests.** A new class passing its unit suite may still break transactions, serialization, or API error propagation. Run tests at all relevant client-visible boundaries.

**Testing only “nice” inputs.** Defects often occur at 0, thresholds, maximum values, empty objects, `null`, or unusual operation orders. Specify the input domain and check boundaries inside and outside it.

**Treating the old implementation as the only specification.** Old code may have bugs; copying them still passes differential tests. Add independently agreed requirement-based examples.

**Coupling tests to class structure.** Legitimate refactoring changes class counts, internal call order, or injection style. Test values, state, exceptions, and meaningful external effects.

**Overusing mocks.** Mocking every dependency and call sequence makes tests brittle when object collaboration changes. Mock at I/O boundaries that should not execute for real, alongside integration tests using representative configuration.

**Using irreproducible random data.** For differential/property tests, use fixed seeds, print failing inputs, and add failures to a deterministic regression suite; do not rely only on random cases.

**Treating all-green tests as proof no regressions exist.** Tests measure only encoded cases/properties; high coverage does not guarantee a valid oracle. Code reviews, integration tests, and risk assessments remain important.

## 10. Practical Exercises

1. Change `>=` to `>` in `StandardShippingRule`; predict and run the affected test.
2. Move validation from `RefactoredCheckout` into `ShippingRule` and deliberately omit one branch. Test inputs -1 and 1.000.001.
3. Add a new `PromotionShippingRule`: assuming **business requirements remain unchanged**, run the same suite to see whether it satisfies the contract.
4. Add `discountCents` to `Invoice` under a **new requirement**; specify the new contract and intentionally update tests, distinguishing a functional change from refactoring.
5. Apply this to a real repository or service: choose a public method, specify inputs/outputs/errors/side effects, write specification tests, then refactor at least two classes while keeping those tests green.

**Acceptance criterion:** You can change an OOP design and verify correct client-visible behavior using specification tests, boundary inputs, and at least one before/after comparison. A regression must cause a test to identify the specific broken input and promise.
