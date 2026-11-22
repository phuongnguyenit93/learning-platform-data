# Testing Subtype Substitutability (Liskov Substitution Principle — LSP)

> **Context:** OOP → Testing. This lesson focuses on **testing that every subtype can replace a superclass/interface at its use sites** without violating promised behavior.

## 1. Learning Outcomes

After this lesson, you can:

- Explain LSP through **behavioral contracts**, not only `extends`/`implements` relationships.
- Separate testable requirements into **preconditions**, **postconditions**, **invariants**, **exceptions**, and **side effects**.
- Design **one reusable contract test suite** for every implementation of an abstraction.
- Test **input-domain boundaries**, combining representative cases with reproducibly seeded generated data.
- Detect LSP violations and distinguish **passing tests** from proving correctness for all possible inputs.

## 2. What Does Subtype Substitution Mean?

Suppose client code depends on abstract type `T`. If `S` is a subtype of `T`, replacing an object of `T` with an `S` **must not break expectations documented in `T`'s contract**.

~~~java
DiscountPolicy policy = new TenPercentDiscount(); // dùng qua interface
Checkout checkout = new Checkout(policy);
long payable = checkout.amountToPay(50_000);
~~~

`Checkout` depends only on `DiscountPolicy`, so every implementing class must honor that interface's shared guarantees.

**Java's type relationship alone cannot guarantee LSP.** The compiler checks method signatures and type constraints; it cannot prove implementations produce correct results, preserve invariants, avoid undocumented exceptions, or prevent unexpected side effects.

| Contract Element | What a Subtype May Do | Violation to Test For |
|---|---|---|
| Preconditions (`precondition`) | Preserve or **weaken** them | Add requirements to inputs valid for the supertype |
| Postconditions (`postcondition`) | Preserve or **strengthen** them | Return out-of-range results or drop promised guarantees |
| Invariants (`invariant`) | Preserve all shared invariants | Enter states forbidden by the abstraction |
| Exceptions | Throw only as promised by the contract | Throw new errors on valid inputs or alter failure semantics |
| Side effects | Preserve observable guarantees | Mutate state, write data, or perform forbidden effects |
| Client observations | Preserve behavior clients legitimately expect | Force clients to use `instanceof` for subtype-specific handling |

For example, if the supertype accepts all amounts from 0 through 1.000.000 cents, a subtype must not arbitrarily reject orders below 50.000 cents. That would **strengthen the precondition** even though compilation still succeeds.

## 3. Choose a Testable Contract

We implement discount calculation in **cents** using `long` to avoid floating-point precision issues in this example.

Contract for `DiscountPolicy.discountCents(subtotalCents)`:

1. **Valid input domain:** `0 <= subtotalCents <= 1_000_000`.
2. **Postcondition:** `0 <= discountCents <= subtotalCents`.
3. Input `0` must produce `0`.
4. For the same object and valid input, results remain consistent; this example requires the policy to have **no mutable state**.
5. No `RuntimeException` is thrown for valid inputs.
6. `Checkout` computes `payable = subtotal - discount` and keeps `payable` within `[0, subtotal]`.

**Contract scope must be explicit.** We make no guarantee for negative inputs or values above 1.000.000; subtypes may reject or additionally support them. Do not invent a rule that “the discount always increases with subtotal,” since valid discount policies have not promised that.

## 4. Runnable Java Example: One Test Suite, Multiple Subtypes

**Requirement: JDK 17 or newer**, without external libraries. Create `LspContractDemo.java` containing all the code below:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.function.Supplier;

public class LspContractDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;

    /**
     * Hợp đồng:
     * - Với 0 <= subtotalCents <= MAX_SUBTOTAL:
     *   trả giá trị trong [0, subtotalCents], không ném RuntimeException.
     * - discountCents(0) == 0.
     * - Không phụ thuộc vào lịch sử gọi (stateless/deterministic).
     * - Không có tác dụng phụ quan sát được bởi client.
     */
    interface DiscountPolicy {
        long discountCents(long subtotalCents);
    }

    // Hợp lệ: không giảm giá.
    static final class NoDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            return 0;
        }
    }

    // Hợp lệ: giảm 10%, làm tròn xuống tới cent.
    static final class TenPercentDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            return subtotalCents / 10;
        }
    }

    // Hợp lệ: chỉ giảm 20% khi đủ ngưỡng.
    // Không giảm dưới ngưỡng vẫn hợp lệ vì hợp đồng cho phép trả 0.
    static final class TieredDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            return subtotalCents >= 50_000 ? subtotalCents / 5 : 0;
        }
    }

    // CỐ Ý SAI: từ chối những subtotal hợp lệ dưới 50_000.
    static final class MinimumOnlyDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            if (subtotalCents < 50_000) {
                throw new IllegalArgumentException("Minimum purchase is 50000");
            }
            return subtotalCents / 10;
        }
    }

    static final class Checkout {
        private final DiscountPolicy policy;

        Checkout(DiscountPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        long amountToPay(long subtotalCents) {
            return subtotalCents - policy.discountCents(subtotalCents);
        }
    }

    // Factory tạo fixture độc lập, tránh dùng chung một object có state.
    record PolicyCase(String name, Supplier<DiscountPolicy> factory) {}

    // Đây chính là contract suite áp cho TẤT CẢ kiểu con.
    static void verifyContract(PolicyCase testCase) {
        DiscountPolicy policy = testCase.factory().get();

        // Biên dưới, biên trên, hai phía ngưỡng nghiệp vụ và lân cận.
        long[] boundaryValues = {
            0, 1, 9, 10, 49_999, 50_000, 50_001, 999_999, 1_000_000
        };

        for (long subtotal : boundaryValues) {
            checkOne(testCase.name(), policy, subtotal);
        }

        // Bổ sung các giá trị trong miền hợp lệ, có thể tái lập nhờ seed.
        Random random = new Random(205L);
        for (int i = 0; i < 500; i++) {
            long subtotal = random.nextInt(1_000_001);
            checkOne(testCase.name(), policy, subtotal);
        }
    }

    static void checkOne(String name, DiscountPolicy policy, long subtotal) {
        try {
            long first = policy.discountCents(subtotal);
            long second = policy.discountCents(subtotal);
            long payable = new Checkout(policy).amountToPay(subtotal);

            require(first >= 0 && first <= subtotal,
                name + ": discount outside [0, subtotal] for " + subtotal);
            require(first == second,
                name + ": same input produced different results at " + subtotal);
            require(subtotal != 0 || first == 0,
                name + ": discount(0) must be zero");
            require(payable == subtotal - first,
                name + ": Checkout cannot rely on stable policy at " + subtotal);
            require(payable >= 0 && payable <= subtotal,
                name + ": invalid amount to pay at " + subtotal);
        } catch (RuntimeException ex) {
            throw new AssertionError(
                name + ": threw exception for valid subtotal " + subtotal, ex
            );
        }
    }

    static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<PolicyCase> validPolicies = List.of(
            new PolicyCase("NoDiscount", NoDiscount::new),
            new PolicyCase("TenPercentDiscount", TenPercentDiscount::new),
            new PolicyCase("TieredDiscount", TieredDiscount::new)
        );

        // Thay thế các kiểu con qua CÙNG interface và CÙNG contract suite.
        for (PolicyCase testCase : validPolicies) {
            verifyContract(testCase);
            System.out.println("PASS: " + testCase.name());
        }

        // Demonstration: bộ kiểm thử phải bắt được implementation sai.
        PolicyCase broken = new PolicyCase(
            "MinimumOnlyDiscount", MinimumOnlyDiscount::new
        );
        boolean detected = false;
        try {
            verifyContract(broken);
        } catch (AssertionError error) {
            detected = true;
            System.out.println("EXPECTED FAIL: " + error.getMessage());
        }
        require(detected, "Broken implementation unexpectedly passed");
        System.out.println("DONE: contract tests detected the LSP violation");
    }
}
~~~

Open a terminal in the file's directory:

~~~powershell
javac LspContractDemo.java
java LspContractDemo
~~~

Expected output (abbreviated):

~~~text
PASS: NoDiscount
PASS: TenPercentDiscount
PASS: TieredDiscount
EXPECTED FAIL: MinimumOnlyDiscount: threw exception for valid subtotal 0
DONE: contract tests detected the LSP violation
~~~

**Why does this test substitutability?** The suite invokes every implementation **through `DiscountPolicy`**, applies the same interface expectations, and exercises them in a real client (`Checkout`). Although `MinimumOnlyDiscount` declares `implements DiscountPolicy`, it throws for `0`, which is valid under the contract. Therefore it cannot safely substitute for the supertype.

The `AssertionError` catch at the end of `main` merely demonstrates an **intentionally incorrect** implementation. In CI and actual project tests, report **FAIL** whenever an implementation violates the contract; do not swallow the failure and report success.

## 5. From the Example to a Project Test Suite

A reusable testing design:

~~~mermaid
flowchart TD
    A["Hợp đồng của interface / lớp cha"] --> B["Bộ test chung"]
    C["Factory: implementation A"] --> B
    D["Factory: implementation B"] --> B
    E["Factory: implementation mới"] --> B
    B --> F["Kiểm tra tiền/hậu điều kiện, bất biến, ngoại lệ"]
    F --> G{"Mọi assertion đều đạt?"}
    G -->|Có| H["Đạt các ca đã kiểm tra"]
    G -->|Không| I["Phát hiện vi phạm hợp đồng"]
~~~

In a project using **JUnit 5**, put `verifyContract` in a helper and run the same assertions using `@TestFactory`/`@ParameterizedTest`. The following example belongs in the same package as `LspContractDemo` with JUnit Jupiter installed:

~~~java
import static org.junit.jupiter.api.DynamicTest.dynamicTest;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

class DiscountPolicyContractTest {
    @TestFactory
    Stream<DynamicTest> everyImplementationRespectsContract() {
        return Stream.of(
            new LspContractDemo.PolicyCase(
                "NoDiscount", LspContractDemo.NoDiscount::new),
            new LspContractDemo.PolicyCase(
                "TenPercentDiscount", LspContractDemo.TenPercentDiscount::new),
            new LspContractDemo.PolicyCase(
                "TieredDiscount", LspContractDemo.TieredDiscount::new)
        ).map(item ->
            dynamicTest(item.name(), () -> LspContractDemo.verifyContract(item))
        );
    }
}
~~~

When adding an implementation, register its **factory** in the test list. When external systems also use the interface, add integration tests at API/storage/network boundaries to check real observable behavior; pure mocks may conceal important differences.

## 6. Designing a More Complete LSP Test Suite

| Case Category | Examples to Verify | Potential LSP Defect |
|---|---|---|
| Boundary values | `0`, `1`, maximum value, just below/above limits | Subtype rejects valid input; off-by-one error |
| Postconditions | `discount >= 0` and `discount <= subtotal` | Negative discount or discount exceeding total |
| Exceptions | Every input in the valid domain | Throws undocumented `IllegalArgumentException` |
| Operation sequences | Repeat one input 2 times; invoke A–B–A | Hidden state makes results depend on call order |
| State invariants | Before/after each operation and after exceptions | Total or state becomes invalid |
| Client observations | Use implementation through interface in `Checkout` | Client must branch on subtype |
| Independence | Create a new object per test when stateful | Test state leaks among implementations |
| Extensibility | Register every implementation selectable at runtime | A new subtype is omitted from the shared suite |

For a **stateful abstraction**, also test operation sequences and post-error state. For example, if `Account.withdraw(x)` promises unchanged balance when withdrawal fails, a subtype that deducts first and then throws violates invariants/postconditions even when its signature matches.

Tests must not require behavior **outside the contract**. For example, they cannot demand that every `DiscountPolicy` give a 10% discount or that two subtypes return identical amounts. Assert that each satisfies **the same guarantees**, not **the same exact results**.

## 7. Common Mistakes in Substitutability Testing

**1. Only checking `instanceof` or using a cast.** This proves a type relationship, not behavioral compatibility. Test through `DiscountPolicy` variables and the same assertions.

**2. Separate, inconsistent standards for each implementation.** Specialized tests are useful for implementation-specific rules but do not replace **the shared contract suite**. If every subtype accepts a different input domain, the abstraction may no longer express a valid shared contract.

**3. Confusing invalid subtype input with invalid supertype input.** A subtype cannot introduce a 50.000 minimum when the shared contract accepts 0.

**4. Checking return values while ignoring exceptions and state.** A subclass may produce correct success results yet mutate data after failure or throw where the client expects success.

**5. Random testing without fixed seeds.** Failures become hard to reproduce. Use fixed seeds in CI, record failing inputs, and include intentional boundary tests. `500` sample inputs **are not mathematical proof** for all inputs.

**6. Replacing contracts with implementation details.** If tests demand an internal data structure, algorithm, or exact discount percentage not promised by the API, they undermine substitutability without a legitimate client requirement.

**7. Weakening an interface to justify a broken subtype.** Sometimes the right solution is to **split the abstraction**: a mandatory writable API should not receive a read-only subtype that throws `UnsupportedOperationException` for every valid write. Consider separate `ReadableRepository` and `WritableRepository` interfaces instead of a contradictory contract.

## 8. Applying This in Code Review and CI

1. **Write verifiable contract statements.** Define valid inputs, outputs, exceptions, invariants, states, and side effects expected by clients.
2. **Put shared assertions in one suite.** Use an interface or superclass in helper signatures, with a factory for each implementation.
3. **Cover boundaries and operation sequences.** For stateful classes, create fresh objects and check rejected operations too.
4. **Run tests when adding/changing subtypes.** When shared tests fail, investigate the subtype and contract rather than automatically rewriting assertions.
5. **Add integration tests for representative clients.** Particularly for transactions, I/O, caches, concurrency, and external APIs.
6. **Acknowledge limits of test claims.** Passing tests establishes only the measured cases/properties; design review and other verification methods remain necessary.

### Practical Exercises

- Add `NegativeDiscount` returning `-1`: identify which postcondition assertion fails.
- Add `MoreThanTotalDiscount` returning `subtotalCents + 1`: identify the violated postcondition and its impact on `Checkout`.
- Add a policy that counts invocations and changes results: identify the consistency test that catches it.
- Modify `MinimumOnlyDiscount` to accept all valid inputs while still giving no discount on small orders; rerun the contract suite to confirm the subtype now complies.
- Choose a real interface (repository, payment gateway, data reader), specify its observable guarantees, and run the same suite against at least two different implementations.

**Completion criterion:** You can add a subtype to the existing contract suite and identify exactly which behavioral conditions would reject it, even if its Java signatures remain entirely valid.
