# Balancing Principles Against Real-World Complexity

**Scope:** OOP — SOLID in Java.  
**Objective:** Learn when to apply a design principle, how extensively to apply it, and when to keep a solution simple so the system stays understandable, testable, and adaptable.

SOLID consists of five object-oriented design guidelines, not laws requiring every class and method to involve interfaces, inheritance, and dependency injection. Good designs meet current needs while keeping future change costs reasonable. Sometimes that means one concise class with a few branches; sometimes it means independent abstractions.

## 1. Why Can Overapplying SOLID Backfire?

The principles encourage managing **dependencies** and **reasons to change**:

| Principle | Key question | Sign of overapplication |
| --- | --- | --- |
| **SRP — Single Responsibility** | Does a module focus on one responsibility and a coherent group of reasons to change? | Splitting every function into a separate class, forcing a simple workflow through many intermediaries. |
| **OCP — Open/Closed** | Is there a stable variation point that needs extension without modifying tested code? | Creating Strategy/Factory/Plugin systems for speculative branches without real requirements. |
| **LSP — Liskov Substitution** | Does every implementation honor the contract and invariants expected by its clients? | Using inheritance solely for code reuse even though a subtype must reject valid base-type operations. |
| **ISP — Interface Segregation** | Must clients depend on capabilities they do not use? | Splitting interfaces into countless one-method types when every client consistently needs the same set of operations. |
| **DIP — Dependency Inversion** | Does important logic depend too heavily on volatile details (database, HTTP, providers)? | Wrapping every simple class in a matching interface and DI configuration despite having one fixed workflow with no substitution need. |

**Separating responsibilities** does not mean "one method per class." **Being open for extension** does not mean "never modify a class." **Programming to abstractions** does not mean "every class needs an interface."

Every abstraction has costs: naming, extra indirection when reading code, dependency management, public-contract maintenance, IDE navigation, mock/fake upkeep, and explanations for teammates. These costs are justified only when they meaningfully reduce change or testing costs.

## 2. Start with a Genuinely Simple Case

Suppose a store's first version offers **only** standard shipping:

- Shipping fee: **30.000 VND**.
- Orders of **500.000 VND** or more ship free.
- There are no third-party APIs or alternative shipping plans yet.
- Monetary amounts are stored as integer VND to avoid floating-point rounding errors.

In this situation, a single class may be appropriate:

~~~java
final class SimpleCheckout {
    long totalVnd(long goodsTotalVnd) {
        if (goodsTotalVnd < 0) {
            throw new IllegalArgumentException("Tổng tiền hàng không hợp lệ");
        }

        long shippingFee = goodsTotalVnd >= 500_000L ? 0L : 30_000L;
        return Math.addExact(goodsTotalVnd, shippingFee);
    }
}
~~~

The code is short, has clear rules, and is easy to debug and test. Immediately introducing **FeePolicy**, **PolicyFactory**, **PolicyRegistry**, and dynamic configuration solely because "more delivery plans *might* be added someday" increases complexity before there is evidence of benefit.

When rules remain few and stable, a handful of simple, testable **if/switch** branches can be a sound choice. Refactor when requirements actually expand, using verified existing behavior as the baseline.

## 3. Designs Should Evolve as Requirements Change

Six months later, the requirements are different:

- **Express** shipping is added with a base fee of 50.000 VND plus 5.000 VND per kilogram, rounding partial kilograms up.
- **Standard** shipping still becomes free for subtotals of at least 500.000 VND.
- The two policies are owned by different business teams and change independently.
- New shipping policies may be connected through configuration.

Now the *independently changing rules* provide a concrete reason to extract an abstraction. The approach could look like this:

~~~mermaid
flowchart TD
    A["Checkout cần tính phí"] --> B["DeliveryFeePolicy (hợp đồng)"]
    B --> C["StandardFeePolicy"]
    B --> D["ExpressFeePolicy"]
    E["Cấu hình chế độ giao hàng"] --> F["Bảng chọn policy"]
    F --> A
~~~

### Complete Java 17+ Example

Save as **DeliveryDemo.java**. The example uses **record**, **enum**, and **Map** to keep the model small while allowing policies to vary independently.

~~~java
import java.util.Map;
import java.util.Objects;

public class DeliveryDemo {
    enum DeliveryMode {
        STANDARD, EXPRESS
    }

    record Order(long goodsTotalVnd, long weightGrams) {
        Order {
            if (goodsTotalVnd < 0 || weightGrams < 0) {
                throw new IllegalArgumentException(
                        "Tiền hàng và khối lượng phải không âm");
            }
        }
    }

    record Receipt(
            long goodsTotalVnd,
            long deliveryFeeVnd,
            long grandTotalVnd
    ) {}

    // Abstraction nhỏ: một chính sách chịu trách nhiệm tính phí.
    interface DeliveryFeePolicy {
        long calculateFeeVnd(Order order);
    }

    static final class StandardFeePolicy implements DeliveryFeePolicy {
        @Override
        public long calculateFeeVnd(Order order) {
            return order.goodsTotalVnd() >= 500_000L
                    ? 0L : 30_000L;
        }
    }

    static final class ExpressFeePolicy implements DeliveryFeePolicy {
        @Override
        public long calculateFeeVnd(Order order) {
            // Phần lẻ kilogram được tính thành một kilogram đầy đủ.
            long grams = order.weightGrams();
            // Ceil(grams / 1000) mà không cộng 999 gây overflow long.
            long kilograms = grams / 1_000L
                    + (grams % 1_000L == 0 ? 0 : 1);
            long weightSurchargeVnd = Math.multiplyExact(kilograms, 5_000L);
            return Math.addExact(50_000L, weightSurchargeVnd);
        }
    }

    static final class Checkout {
        private final Map<DeliveryMode, DeliveryFeePolicy> policies;

        Checkout(Map<DeliveryMode, DeliveryFeePolicy> policies) {
            this.policies = Map.copyOf(
                    Objects.requireNonNull(policies));
        }

        Receipt price(Order order, DeliveryMode mode) {
            Objects.requireNonNull(order, "order");
            Objects.requireNonNull(mode, "mode");

            DeliveryFeePolicy policy = policies.get(mode);
            if (policy == null) {
                throw new IllegalArgumentException(
                        "Chưa cấu hình chính sách cho: " + mode);
            }

            long fee = policy.calculateFeeVnd(order);
            if (fee < 0) {
                throw new IllegalStateException(
                        "Chính sách trả về phí âm");
            }

            long total = Math.addExact(order.goodsTotalVnd(), fee);
            return new Receipt(order.goodsTotalVnd(), fee, total);
        }
    }

    public static void main(String[] args) {
        Checkout checkout = new Checkout(Map.of(
                DeliveryMode.STANDARD, new StandardFeePolicy(),
                DeliveryMode.EXPRESS, new ExpressFeePolicy()
        ));

        Order order = new Order(600_000L, 1_500L);
        System.out.println(checkout.price(order, DeliveryMode.STANDARD));
        System.out.println(checkout.price(order, DeliveryMode.EXPRESS));
    }
}
~~~

Run:

~~~bash
javac DeliveryDemo.java
java DeliveryDemo
~~~

Output:

~~~text
Receipt[goodsTotalVnd=600000, deliveryFeeVnd=0, grandTotalVnd=600000]
Receipt[goodsTotalVnd=600000, deliveryFeeVnd=60000, grandTotalVnd=660000]
~~~

In this design:

1. **SRP:** Each policy contains the fee rule for one delivery mode; **Checkout** coordinates policy selection and total calculation.
2. **OCP:** New policy implementations can be added without editing total-calculation logic in **Checkout**. Adding a mode to **DeliveryMode**, updating configuration, and adjusting related components may still require changes—OCP does not make the entire system immutable when features are added.
3. **LSP:** Policies must honor a consistent contract: return valid, nonnegative fees for valid orders without arbitrarily mutating order objects. A policy that reports false success or negative fees is not safely substitutable.
4. **ISP:** **Checkout** only needs **calculateFeeVnd**. Policies are not forced to send email, export invoices, or persist data.
5. **DIP:** **Checkout** depends on **DeliveryFeePolicy** rather than directly on **StandardFeePolicy** or **ExpressFeePolicy**. Configuration in **main** (the composition root) determines the implementation to supply.

**Intentional limitation:** A simple **enum** and registry suffice for the two modes in this example. If real requirements have only two very stable branches, a clear **switch** may still cost less than two policy classes and a registry. The abstraction becomes worthwhile when policies evolve, are tested, and are replaced independently.

## 4. What Should Be Tested to Justify the Separation?

Test **meaningful behavior**, not internal structure just to prove how many classes exist. With JUnit Jupiter (JUnit 5), the following cases exercise business boundaries and calculations:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import org.junit.jupiter.api.Test;

class DeliveryDemoTest {
    @Test
    void standardMiễnPhíKhiĐạtNgưỡng() {
        var checkout = new DeliveryDemo.Checkout(Map.of(
                DeliveryDemo.DeliveryMode.STANDARD,
                new DeliveryDemo.StandardFeePolicy()));

        var result = checkout.price(
                new DeliveryDemo.Order(500_000L, 1_800L),
                DeliveryDemo.DeliveryMode.STANDARD);

        assertEquals(0L, result.deliveryFeeVnd());
        assertEquals(500_000L, result.grandTotalVnd());
    }

    @Test
    void expressLàmTrònLênTheoKilogram() {
        var policy = new DeliveryDemo.ExpressFeePolicy();

        assertEquals(50_000L, policy.calculateFeeVnd(
                new DeliveryDemo.Order(100_000L, 0L)));
        assertEquals(55_000L, policy.calculateFeeVnd(
                new DeliveryDemo.Order(100_000L, 1L)));
        assertEquals(60_000L, policy.calculateFeeVnd(
                new DeliveryDemo.Order(100_000L, 1_001L)));
        // Với khối lượng cực lớn, phí tràn long phải báo lỗi,
        // không tạo ra số kilogram âm do phép cộng bị overflow.
        assertThrows(ArithmeticException.class, () ->
                policy.calculateFeeVnd(
                        new DeliveryDemo.Order(100_000L, Long.MAX_VALUE)));
    }

    @Test
    void chưaCấuHìnhPolicyPhảiBáoLỗiRõRàng() {
        var checkout = new DeliveryDemo.Checkout(Map.of());

        assertThrows(IllegalArgumentException.class, () ->
                checkout.price(
                        new DeliveryDemo.Order(50_000L, 100L),
                        DeliveryDemo.DeliveryMode.EXPRESS));
    }
}
~~~

**Note:** These tests require JUnit Jupiter on the project's classpath. The rounding rule in the example is an illustrative business assumption. If a carrier specifies a minimum kilogram, volumetric weight, monetary rounding, or regional surcharges, update the specification and tests accordingly before changing implementations.

A fake **DeliveryFeePolicy** can be passed to **Checkout** to verify total calculation without invoking a real shipping service. However, if the entire logic is one stable formula, directly testing a pure function may be sufficient; creating an interface solely for mocking is unnecessary.

## 5. Choosing Between Simplicity and Extensibility

A design technique is worthwhile only when it addresses *specific change pressures*. The following table can guide reviews:

| Real-world situation | Approach to consider | Why |
| --- | --- | --- |
| One small rule that rarely changes | Pure function or simple class | Fewer concepts; easy to read and test. |
| Two variants with short, stable conditions | Clear, tested **if/switch** | Lower total cost than Strategy/Factory may be possible. |
| Many algorithms serving the same role and varying independently | **Strategy** or a policy interface | Isolates change impact and supports per-algorithm tests. |
| Important business logic calls replaceable database/HTTP services | Port/repository interface at the appropriate boundary | Reduces infrastructure coupling and enables isolated business tests. |
| Reader and writer clients have different needs | Separate read/write interfaces when warranted | Avoids forcing clients to depend on unused operations. |
| One class calculates prices, sends email, accesses DB, and renders PDFs | Split responsibilities with different reasons to change | Isolates failures and change impact. |
| Inheritance forces a subclass to throw **UnsupportedOperationException** | Revisit the subtype; prefer composition or a suitable contract | Preserves behavioral promises to clients. |
| Many interface layers wrap a small immutable model | Consolidate/remove intermediaries without value | Reduces navigation depth and synchronization costs. |

Do not decide solely by **line count**, **class count**, or **interface count**. A coherent module with many lines may be better than a deeply layered design requiring readers to open 12 files to understand one calculation.

### Questions Before Creating an Abstraction

- **Who are the clients?** Which clients need different operations or rules?
- **What actually varies?** Are there two or more existing cases, confirmed requirements, or recurring changes?
- **Where is the boundary?** Do business changes vary independently from databases, protocols, UIs, or providers?
- **Is there a shared contract?** Do implementations honor one behavioral contract or merely share a name?
- **What does the simple approach cost?** How many places must change to add a variant, and how many regression tests are affected?
- **What does abstraction cost?** How many types, DI configurations, implementation-selection rules, API versions, and readability risks does it introduce?

**No fixed number determines the abstraction threshold.** "Wait for three cases before abstracting" can help prevent excessive upfront design, but it is not a law. A payment, legal, or external-integration boundary may warrant separation immediately because its independence and change risk are already clear.

## 6. Three Kinds of Complexity to Recognize

### 6.1. Inherent Business Complexity

For example, delivery depends on distance, weight, peak hours, geographic region, free-shipping conditions, and refund rules. Design patterns cannot make these requirements disappear. We must represent them as explicit, tested rules.

### 6.2. Complexity Introduced by Implementation

Examples include the same formula duplicated in a controller, service, repository, and frontend, or a client calling through five adapters that add no value. Reduce this complexity by centralizing rules, separating dependencies at appropriate boundaries, and removing unnecessary intermediaries.

### 6.3. Complexity Added for Speculative Future Needs

For example, supporting hundreds of dynamically loaded shipping plugins before the project has a second carrier. Here, **YAGNI** (*You Aren't Gonna Need It*) suggests postponing reversible decisions. However, delaying design does not mean ignoring known architectural flaws; high-risk future changes or data incompatibility may justify early investment.

**KISS** (*Keep It Simple*) encourages choosing the simplest solution that meets requirements. **DRY** (*Don't Repeat Yourself*) cautions against duplicating knowledge/rules that may diverge; it does not require merging all syntactically similar code. Combining two similar-looking rules owned by different business stakeholders can create dangerous coupling.

## 7. Assessing Design Quality Through the Consequences of Change

Instead of asking "have we applied all five SOLID letters?", evaluate representative change scenarios.

| Signal | What to observe | Careful interpretation |
| --- | --- | --- |
| **Change surface** | How many modules and public contracts must change for a small request? | Editing multiple places is not automatically bad, but may reveal unnecessary coupling. |
| **Testability** | Do error/edge-case tests require excessive infrastructure setup? | Easy testing often signals good boundaries; too many mocks can hide an unclear design. |
| **Readability** | Can a newcomer quickly trace data flow and business rules? | Forwarding layers without logic add cognitive cost. |
| **Substitutability** | Do replacement adapters, payment methods, or policies honor contracts? | Extensibility matters only when the variation point is real. |
| **Regression risk** | Which tests establish old and new behavior after a change? | Good design works alongside specifications and tests; it does not replace them. |
| **Operational cost** | Does configuration, dependency management, bean initialization, or tracing/debugging increase? | Patterns may shift cost from code into configuration and operations. |

No single score fits all projects. A public library used by many teams usually needs different boundaries from a one-off internal script.

## 8. Refactor Based on Evidence, Not Fashion

A controlled sequence:

1. **Document existing behavior** and protect it with tests covering main cases, boundaries, and errors.
2. **Identify observed reasons to change:** Two rules have different release schedules, a database adapter changes frequently, or a client depends on unused operations.
3. **Choose the narrowest boundary** that actually makes change easier; use domain names rather than merely appending **Manager**, **Processor**, or **Factory**.
4. **Refactor in small steps**, preserving business results for existing inputs and running tests after each impactful change.
5. **Add the new variant** through the newly stabilized contract and verify that existing logic need not be changed broadly.
6. **Remove obsolete classes/adapters** when no clients depend on them; public APIs require compatibility and migration plans.

In Java/Spring, dependency injection supplies implementations through constructors, but DI containers do not decide architectural boundaries. A simple value or pure helper does not need to become a Spring bean just to "follow DIP." Interfaces are often useful with multiple implementations, infrastructure boundaries, public contracts requiring stability, or clients with different needs.

### Mistakes to Watch for During Reviews

- **Speculative generality:** Adding plugin registries, layered overrides, or complex generics before requirements exist.
- **Premature optimization:** Optimizing or restructuring before measuring real performance problems.
- **Shotgun surgery:** A small rule change requires touching many unrelated modules.
- **Feature envy/God class:** One class reads and manipulates too many other classes' states to make business decisions.
- **Inheritance misuse:** A subclass violates its base type's preconditions, postconditions, or invariants.
- **Implementation-coupled tests:** Testing internal call order rather than business outcomes, so behavior-preserving refactors still break tests.

## 9. Practice Exercise

An application initially provides a fixed 5% discount to every customer, then adds discounts by membership tier and promotional code.

**Exercise requirements:**

1. Implement the first version with one function calculating the discount amount, using integers or **BigDecimal** with an explicit rounding rule.
2. Add membership tiers using **if/switch** and tests; determine when the logic remains easy to understand.
3. Simulate changing business requirements: Each promotion has its own lifecycle and eligibility checks. Consider **DiscountPolicy**, but only when multiple policies genuinely need to change independently.
4. Verify **LSP**: Do all policies share input requirements and return nonnegative discounts no greater than the subtotal?
5. Count the files/classes needing edits when a new program is added; simplify again if complexity increases without reducing the cost of change.

**Self-assessment criteria:** The solution meets business requirements, preserves important invariants, tests edge cases, uses an appropriate number of abstractions for known changes, and lets others understand data flow without navigating meaningless layers.

**Core message:** SOLID helps manage dependencies and the cost of change. Apply principles where real risks exist, keep designs small for small problems, and expand abstractions when requirements materialize or strong evidence justifies them.
