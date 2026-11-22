# Overusing design patterns and premature abstraction

**Topic:** OOP → Design Pitfalls  
**Objective:** Recognize when a Design Pattern or abstraction solves a real problem and when it only adds complexity; start with a simple design, identify change pressure, and refactor safely with Java and tests instead of engineering for unverified assumptions.

## 1. Does "good design" necessarily require many classes and interfaces?

Imagine a store's initial requirement:

> Orders below 500.000 VND incur 30.000 VND in shipping fees; orders of at least 500.000 VND ship free.

One implementation:

~~~java
static long shippingFeeVnd(long goodsTotalVnd) {
    if (goodsTotalVnd < 0) {
        throw new IllegalArgumentException("Tiền hàng không được âm");
    }
    return goodsTotalVnd >= 500_000L ? 0L : 30_000L;
}
~~~

For this rule, a short, well-named, tested method may be **the best current design**. It is not less object-oriented simply because it lacks Strategy, Abstract Factory, an interface, or dependency injection.

Yet a developer might think:

> "There will surely be many shipping policies later. Let's prebuild `ShippingPolicy`, `AbstractShippingPolicy`, `PolicyFactory`, `PolicyRegistry`, `PolicyResolver`, `ShippingPolicyConfiguration`, and a plugin framework."

With only one formula, readers must open many files to understand a single `if`. Every new type becomes a maintenance, naming, testing, and documentation commitment.

This is **pattern overuse** and may also be **premature abstraction**: paying for flexibility the project has not demonstrated it needs.

Crucially, **patterns are not inherently bad**, and **fewer classes are not always better**. An abstraction around payments, authorization, or external providers can be valuable immediately when requirements justify it. Evaluate **benefits against costs in the actual context**, not the number of patterns.

## 2. Two related but distinct design smells

### Pattern overuse

Applying a pattern **to the wrong problem**, **at the wrong scale**, or **at the wrong time** can scatter behavior across many components without proportional benefits.

Examples:

- Using **Singleton** for every service despite needing isolated tests and different configurations.
- Using **Abstract Factory** for one object type that only needs a constructor.
- Using **Observer/Event Bus** for one synchronous domain call, making control flow harder to trace without multiple subscribers.
- Layering **Decorators** around one fixed check, obscuring processing order and errors.
- Using **Strategy + Registry** for two very short, rarely changing conditional branches.

A pattern describes a way for objects to collaborate; it does not certify architectural quality.

### Premature abstraction

Generalizing one or a few current cases into a reusable API **before understanding what changes and what stays stable**.

For example, two features both send emails today but may have different purposes later:

- `sendPasswordResetEmail(...)`: expiration, security, and abuse prevention.
- `sendMarketingEmail(...)`: unsubscribe, consent, campaigns, and frequency.

Combining them under `UniversalEmailWorkflow<T, Context, Policy>` solely because both use SMTP can force different responsibilities together. **Similar code does not necessarily mean shared domain knowledge.**

### Comparison

| Criterion | Pattern overuse | Premature abstraction |
| --- | --- | --- |
| Core mistake | Choose a design mechanism larger than required | Predict variation points without enough evidence |
| Example | Factory for `return new User(...)` | Generic `BaseRepository<T, K, V>` for one entity |
| Cost | Many types, forwarding layers, configuration, and tracing | Vague contracts needing flags/branches as real needs arise |
| Consequence | Code looks "architected" but is difficult to read | New cases have to distort old abstractions |
| Remedy | Remove intermediate layers without value | Learn from real use cases, then extract the correct responsibility |

Both problems often appear together: someone predicts 20 future fee algorithms and builds Factory + Strategy + plugin architecture when there is currently one.

## 3. The true cost of an abstraction

A tiny interface may look nearly free:

~~~java
interface FeePolicy {
    long calculateFee(Shipment shipment);
}
~~~

But **design costs** extend beyond these three lines:

| Cost type | What to consider |
| --- | --- |
| **Comprehension** | How many types and configuration classes must be opened to understand one operation? |
| **Change** | Does one new requirement force edits to interfaces, implementations, factories, registries, and test fixtures? |
| **Compatibility** | Is the interface public to other modules, making it hard to change? |
| **Domain language** | Is the abstraction named for a real domain concept rather than generic `Manager`, `Handler`, `Provider`? |
| **Testing** | Does it isolate external dependencies and improve tests, or create dozens of pointless mocks? |
| **Operations** | Does DI setup, implementation selection, diagnosis, logging, or tracing become more complex? |
| **Evolution** | If future assumptions prove false, must the API be removed or heavily changed? |

**An abstraction is valuable when it hides a changeable decision behind a stable, understandable contract.** If it merely forwards a call without dividing responsibility or containing change, it may be unnecessary indirection.

The converse matters too: an object is not expensive merely because it has many lines, and an abstraction is not worthless merely because **one implementation** currently exists. Separating a bank integration port from domain logic may protect an important boundary with just one bank.

## 4. KISS, YAGNI, DRY, and SOLID: avoid extremes

| Principle | Practical meaning | Common misinterpretation |
| --- | --- | --- |
| **KISS** | Choose the simplest correct solution that meets requirements and remains maintainable | "The fewer files, the better" |
| **YAGNI** (*You Aren't Gonna Need It*) | Do not build capabilities without a sufficiently clear need | "Never design any boundaries in advance" |
| **DRY** (*Don't Repeat Yourself*) | Avoid duplicating **knowledge/rules** that must change consistently | "Merge any two similar-looking code blocks" |
| **SRP** | A module has coherent responsibilities and reasons to change | "One method per class" |
| **OCP** | Reduce modifications to stable code when adding variation at suitable extension points | "Never modify an existing class" |
| **DIP** | Keep important logic independent from unstable details | "Every class must have a corresponding interface" |

These principles are not inherently contradictory; they address different questions.

For example, **DIP** may suggest an interface for an external payment gateway because it is an important changing boundary. But **YAGNI** discourages building auto-discovery for 20 gateways without a real requirement.

**DRY is about meaning.** Two functions with 8 lines each should not automatically be merged into one with 6 boolean parameters; if they implement independent domain policies, keeping them separate may support correct evolution.

### Do not turn the "Rule of Three" into law

A practical heuristic is to observe a few similar cases before extracting abstractions. But the numbers 2, 3, and 4 **do not prove** anything by themselves.

If two confirmed clients require one stable contract, an abstraction may be worthwhile immediately. If three code fragments look alike but have separate owners and reasons to change, extracting a shared interface may be wrong.

**A better criterion than repetition count: must these cases genuinely change together?**

## 5. Evolving from one condition to a justified extension point

### Stage 1 — only one shipping policy is required

Suppose a store initially offers only **STANDARD** shipping, free from 500.000 VND, otherwise 30.000 VND.

A simple version with validation and overflow protection:

~~~java
static long checkoutTotalVnd(long goodsTotalVnd) {
    if (goodsTotalVnd < 0) {
        throw new IllegalArgumentException("Tổng tiền hàng âm");
    }
    long fee = goodsTotalVnd >= 500_000L ? 0L : 30_000L;
    return Math.addExact(goodsTotalVnd, fee);
}
~~~

**There is nothing wrong** with starting here. The API is readable, results are obvious, and tests are quick. Prebuilding `PolicyFactory` does not improve the arithmetic.

### Stage 2 — a real variant appears

Later, confirmed requirements arise:

- **STANDARD:** the existing rule.
- **EXPRESS:** a fixed 50.000 VND fee plus 5.000 VND per kilogram, rounding partial kilograms up.
- Separate business groups own the two policies, which may evolve independently.

At least two approaches now make sense:

**Option A — keep a `switch`:** if the formulas are short, share an owner, and rarely change, a tested `switch` can be clear.

**Option B — extract `FeePolicy`:** if algorithms grow, are tested/deployed independently, or gain separate fee providers, Strategy becomes useful. We can now see a **real variation point** instead of guessing.

~~~mermaid
flowchart TD
    A["Một chính sách đơn giản"] --> B{"Có biến thể thật hoặc ranh giới độc lập?"}
    B -->|"Chưa"| C["Hàm/điều kiện rõ nghĩa + test"]
    B -->|"Có"| D{"Các nhánh còn ngắn và cùng thay đổi?"}
    D -->|"Có"| E["Cân nhắc switch + test"]
    D -->|"Không"| F["Policy interface + implementation riêng"]
    C --> G["Quan sát tác động thay đổi"]
    E --> G
    F --> G
    G --> H["Refactor khi có bằng chứng mới"]
~~~

This is **a decision process**, not a mechanical formula. Good structure depends on change risks and code lifecycle.

## 6. Standalone Java 17 example: comparing a simple design and Strategy

Save as **AbstractionTimingDemo.java**. The file contains:

1. `SimpleCheckout` for the initial stage;
2. `FeePolicy`, `StandardFee`, `ExpressFee`, and `PolicyCheckout` for the variant stage;
3. `Shipment` for validated input data.

The example does **not claim that Strategy is always better**. It shows when an abstraction starts serving a real purpose.

~~~java
import java.util.Map;
import java.util.Objects;

public class AbstractionTimingDemo {

    public record Shipment(long goodsValueVnd, long weightGrams) {
        public Shipment {
            if (goodsValueVnd < 0 || weightGrams < 0) {
                throw new IllegalArgumentException(
                        "Giá trị hàng và khối lượng không được âm");
            }
        }
    }

    // Giai đoạn 1: không có nhu cầu hoán đổi thuật toán.
    public static final class SimpleCheckout {
        public long totalVnd(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            long fee = shipment.goodsValueVnd() >= 500_000L
                    ? 0L : 30_000L;
            return Math.addExact(shipment.goodsValueVnd(), fee);
        }
    }

    public enum Mode {
        STANDARD, EXPRESS
    }

    // Giai đoạn 2: một hợp đồng tính phí cho các chính sách
    // thay đổi độc lập. Interface này chỉ cần đúng một năng lực.
    @FunctionalInterface
    public interface FeePolicy {
        long feeVnd(Shipment shipment);
    }

    public static final class StandardFee implements FeePolicy {
        @Override
        public long feeVnd(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            return shipment.goodsValueVnd() >= 500_000L
                    ? 0L : 30_000L;
        }
    }

    public static final class ExpressFee implements FeePolicy {
        @Override
        public long feeVnd(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");

            // Không dùng weightGrams + 999 để tránh overflow.
            long kilograms = shipment.weightGrams() / 1_000L;
            if (shipment.weightGrams() % 1_000L != 0) {
                kilograms = Math.addExact(kilograms, 1L);
            }

            long surcharge = Math.multiplyExact(kilograms, 5_000L);
            return Math.addExact(50_000L, surcharge);
        }
    }

    public static final class PolicyCheckout {
        private final Map<Mode, FeePolicy> policies;

        public PolicyCheckout(Map<Mode, FeePolicy> policies) {
            this.policies = Map.copyOf(
                    Objects.requireNonNull(policies, "policies"));
        }

        public long totalVnd(Mode mode, Shipment shipment) {
            Objects.requireNonNull(mode, "mode");
            Objects.requireNonNull(shipment, "shipment");

            FeePolicy policy = policies.get(mode);
            if (policy == null) {
                throw new IllegalArgumentException(
                        "Chưa cấu hình chế độ: " + mode);
            }

            long fee = policy.feeVnd(shipment);
            if (fee < 0) {
                throw new IllegalStateException(
                        "Chính sách trả về phí âm");
            }

            return Math.addExact(shipment.goodsValueVnd(), fee);
        }
    }

    public static void main(String[] args) {
        Shipment shipment = new Shipment(600_000L, 1_500L);

        SimpleCheckout initial = new SimpleCheckout();
        System.out.println(
                "Initial: " + initial.totalVnd(shipment));

        PolicyCheckout evolved = new PolicyCheckout(Map.of(
                Mode.STANDARD, new StandardFee(),
                Mode.EXPRESS, new ExpressFee()
        ));
        System.out.println(
                "Standard: " + evolved.totalVnd(Mode.STANDARD, shipment));
        System.out.println(
                "Express: " + evolved.totalVnd(Mode.EXPRESS, shipment));
    }
}
~~~

Run:

~~~bash
javac AbstractionTimingDemo.java
java AbstractionTimingDemo
~~~

Output:

~~~text
Initial: 600000
Standard: 600000
Express: 660000
~~~

**Formula check:** a 600.000 VND order gets free STANDARD shipping. For EXPRESS, 1.500 g rounds up to **2 kg**, giving a fee of 50.000 + 2 × 5.000 = **60.000 VND**, and a total of 660.000 VND.

### What changes between the two stages?

| Before confirmed variation | After confirmed variation |
| --- | --- |
| One formula, one place to edit | Two algorithms can evolve independently |
| No implementation selection required | `Mode`/composition root chooses the policy |
| A simple function is enough | `FeePolicy` becomes a meaningful contract |
| A few direct tests | Separate policy tests and orchestration tests |
| Fewer forwarding layers | An abstraction reduces coupling among algorithms |

**Not every additional mode needs Strategy.** If the logic remains a few statements owned by one team, a `switch` may cost less. Here, Strategy appears because the policies are assumed to **change independently**, not merely because an `enum` has two values.

Extensibility has limits: adding a new shipping mode may still require updating `Mode` and a `Map` configuration. OCP does not promise "never edit any file"; it encourages changes at appropriate extension points.

## 7. Testing preserves behavior during refactoring

When extracting policies from a function, do not assume the new code is "more correct" just because it looks architecturally sophisticated. Capture **existing behavior** in tests and then verify the new branch:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;

class AbstractionTimingDemoTest {

    @Test
    void logicStandardCuVanDungSauKhiTachPolicy() {
        var oldCheckout = new AbstractionTimingDemo.SimpleCheckout();
        var newCheckout = new AbstractionTimingDemo.PolicyCheckout(
                Map.of(AbstractionTimingDemo.Mode.STANDARD,
                        new AbstractionTimingDemo.StandardFee()));

        long[] totals = {0L, 100_000L, 499_999L, 500_000L, 750_000L};

        for (long goodsValueVnd : totals) {
            var request = new AbstractionTimingDemo.Shipment(
                    goodsValueVnd, 1_000L);

            assertEquals(
                    oldCheckout.totalVnd(request),
                    newCheckout.totalVnd(
                            AbstractionTimingDemo.Mode.STANDARD,
                            request)
            );
        }
    }

    @Test
    void expressLamTronTheoKilogram() {
        var policy = new AbstractionTimingDemo.ExpressFee();

        assertEquals(50_000L,
                policy.feeVnd(new AbstractionTimingDemo.Shipment(
                        100_000L, 0L)));
        assertEquals(55_000L,
                policy.feeVnd(new AbstractionTimingDemo.Shipment(
                        100_000L, 1L)));
        assertEquals(60_000L,
                policy.feeVnd(new AbstractionTimingDemo.Shipment(
                        100_000L, 1_500L)));
    }

    @Test
    void thieuChinhSachPhaiBaoLoiRoRang() {
        var checkout = new AbstractionTimingDemo.PolicyCheckout(
                Map.of());

        assertThrows(IllegalArgumentException.class, () ->
                checkout.totalVnd(
                        AbstractionTimingDemo.Mode.EXPRESS,
                        new AbstractionTimingDemo.Shipment(
                                100_000L, 1_000L)));
    }

    @Test
    void dauVaoAmBiTuChoi() {
        assertThrows(IllegalArgumentException.class, () ->
                new AbstractionTimingDemo.Shipment(-1L, 0L));
    }
}
~~~

The test file is **AbstractionTimingDemoTest.java**, requiring JUnit Jupiter 5 on the classpath. The demo itself only requires JDK 17.

What do these tests establish?

- The STANDARD formula **does not change** when extracted from a function into an interface implementation.
- EXPRESS rounds weights according to the documented rule.
- Missing registry implementations produce clear errors.
- Invalid input is rejected before calculation.

**A passing test count cannot prove architectural quality.** Tests primarily support safe changes; complexity and readability need separate review. Do not mock every helper merely for "testability": pure functions are already easy to test directly.

## 8. Signs that abstraction has gone too far

### 8.1. An interface per class without a clear boundary

For example:

~~~text
UserController
  → IUserService
  → UserServiceImpl
  → IUserManager
  → UserManagerImpl
  → IUserRepository
  → UserRepositoryImpl
~~~

This chain is **not automatically bad**: a service with business rules and a repository separating infrastructure can be appropriate. But if each layer merely forwards calls without distinct responsibilities, policies, or replacement points, the layers add work without value.

**Ask:** would removing an interface/intermediary lose a real capability (module boundary, public contract, adapter replacement, isolated testing, authorization)? If not, simplify.

Java does not require interfaces for unit tests. Test concrete classes directly, or use fakes for real external-dependency boundaries.

### 8.2. A generic framework for one problem

~~~java
// Ý tưởng đáng ngờ nếu chỉ dùng với đúng một màn hình CRUD:
// AbstractWorkflowCoordinator<T, ID, META, POLICY, CONTEXT>
~~~

This generic framework burdens API users with type parameters, factories, converters, hooks, configuration, and lifecycle concerns. Without several workflows genuinely sharing one contract, its parameters may simply encode **an incomplete understanding of the problem**.

A powerful abstraction need not be broad. A carefully designed two-method `PaymentGateway` interface can be more valuable than a "universal" framework with twenty extension points.

### 8.3. A configuration system replaces one condition

If changing a free-shipping threshold requires edits to YAML, registry keys, factory mappings, and bean profiles, abstraction may have **moved complexity from Java to configuration** without reducing it.

Dynamic configuration is useful when policies **must change without a code release**, differ by tenant, or select implementations by environment. Otherwise a clear constant/domain setting may suffice.

### 8.4. Abstractions that leak implementation details

A `StoragePort` meant to separate business code from the database fails to hide infrastructure if its API exposes `JdbcConnection`, SQL column names, and transaction drivers. A `NotificationSender` that accepts vendor-specific objects also couples business logic to an SDK.

**The better direction** is to express capabilities in client-side domain terms and let adapters translate them to external APIs.

## 9. Distinguish "duplicated code" from "duplicated knowledge"

Consider two policies with identical formulas today:

~~~java
long loyaltyDiscount(long amountVnd) {
    return amountVnd * 5 / 100;
}

long seasonalDiscount(long amountVnd) {
    return amountVnd * 5 / 100;
}
~~~

Both currently use 5% but may have **different reasons to change**:

- Loyalty discounts change with retention policy.
- Seasonal discounts change with marketing campaigns.

Combining them into `universalDiscount(amount, isLoyalty, isSeasonal, ...)` couples unrelated policies in one function. This is **accidental syntactic similarity**, not necessarily shared knowledge.

Conversely, if both follow a **company-wide money-rounding rule**, extracting a small rounding helper may be right: the **rounding policy** genuinely is shared and must remain consistent.

**Questions to investigate:**

1. When requirement A changes, should requirement B change too?
2. Do the cases share an owner and domain vocabulary?
3. Is there a genuine shared invariant or contract?
4. Does the new abstraction's name reflect a domain concept?
5. How many flags/branches are required for both A and B?

If an abstraction repeatedly acquires flags such as `isSpecial`, `skipValidation`, and `useLegacyMode`, its cases may no longer share a healthy contract.

## 10. Questions to answer before choosing a Design Pattern

| Pattern or mechanism | Evidence to look for | Overuse warning |
| --- | --- | --- |
| **Strategy** | Algorithms fulfilling one role need interchangeable, independently changing implementations | Only one short formula |
| **Factory Method/Abstract Factory** | Object selection/construction has real logic; several related object families | Factory only invokes a constructor |
| **Builder** | Numerous optional arguments, validated combinations, or staged construction | Object with 2–3 straightforward fields |
| **Decorator** | Compose behaviors around objects under a shared interface | Wrapper merely forwards `return next.call()` |
| **Observer/Event** | Independent subscribers react; publish/subscribe decoupling is needed | A direct synchronous call would suffice |
| **State** | Complex lifecycle-dependent behavior and transition tables | Two states and one `if` |
| **Repository/Port** | Business code requires isolation from storage, infrastructure, or a public contract | Interface copies a class API 1:1 without adding a boundary |
| **Dependency Injection** | Explicit dependency supply and lifecycle configuration are needed | Bean container for pure calculations without dependencies |
| **Inheritance** | Genuine subtype relationship preserving the LSP contract | Merely reusing 5 lines of code |

This table is not a mechanical pattern-selection rule. It guards against choosing **pattern names** before understanding **change pressure**.

## 11. Evidence-based refactoring process

### Step 1 — describe existing behavior

Document inputs, outputs, preconditions, postconditions, and boundaries first. For shipping, test the 500.000 threshold, 1 VND below it, free shipping, weight = 0, and fractional-kilogram rounding.

### Step 2 — record actual changes

Repeated edits to one variation point are good evidence: adding fee algorithms, switching payment providers, adding authorization models, or two teams needing different versions of a capability.

There is no need to wait for production incidents before refactoring, but neither should we build a plugin engine for a feature absent from an approved roadmap.

### Step 3 — identify what stays stable and what varies

For example:

- Stable: `checkout` requires **a valid fee amount**.
- Variable: the **fee calculation** for each policy.
- Extract `FeePolicy` at this boundary rather than an oversized "ShippingFramework" managing prices, addresses, warehouses, vouchers, and carriers.

### Step 4 — refactor incrementally with regression tests

Preserve existing behavior tests, extract a small contract, migrate the original implementation, add the variant, and rerun tests. Avoid simultaneously renaming every API, persistence layer, protocol, and business rule without reason.

### Step 5 — assess friction after the change

Do not merely ask "did we apply SOLID?" Ask:

- To add a variant, **how many places and public contracts require editing?**
- Must new developers open many files to follow one formula?
- Do logic tests require huge mock graphs?
- Have runtime failures from configuration or decorator order increased?
- Are there abstractions with no clients or remaining purpose?

If refactoring only turns each `if` into an empty class without improving the actual change scenario, reconsider and simplify.

~~~mermaid
flowchart LR
    A["Yêu cầu có thật"] --> B["Giải pháp rõ nhất đáp ứng yêu cầu"]
    B --> C["Test bất biến và ca biên"]
    C --> D["Quan sát thay đổi"]
    D --> E{"Có điểm biến thiên / coupling gây chi phí?"}
    E -->|"Chưa"| F["Giữ thiết kế nhỏ"]
    E -->|"Có"| G["Trích abstraction tối thiểu"]
    G --> H["Đo lại độ dễ đổi, test và đọc"]
    F --> D
    H --> D
~~~

## 12. Cases where early abstraction is intentional and worthwhile

**YAGNI does not mean "no design."** Some boundaries justify early investment because requirements/risks are already established:

- **Public APIs:** many clients will depend on the contract, making breaking changes costly.
- **Provider integrations:** third-party SDKs change and have network timeouts, retry policies, and permissions; business-oriented ports isolate them.
- **Security and authorization:** clear trust boundaries prevent paths bypassing mandatory checks.
- **Money, transactions, and critical data:** early value types, invariants, and transaction boundaries can prevent costly inconsistencies.
- **Core-domain testability:** isolate clocks (`Clock`), randomness, or network APIs when they genuinely undermine deterministic tests.
- **Independent teams or modules:** define verified stable contracts rather than assuming "countless future modules."

The shared feature is **evidence of change costs or risks**. A small example does not imply every abstraction in application architecture is wasteful.

## 13. Overengineering in Java and Spring

Concrete examples:

**Creating an interface for every `@Service` solely for Spring injection** is unnecessary: Spring can constructor-inject concrete classes. Interfaces should represent meaningful contracts, multiple implementations, or module/infrastructure boundaries, not decoration.

**Making every helper a bean** increases container coupling when a pure method or value object could be created and tested directly. Not all Java code needs to be "managed by Spring."

**Using `@Lazy` to bypass circular dependencies** may allow startup without fixing responsibility cycles among services. Revisit dependency direction and orchestration rather than treating deferred initialization as an architectural repair.

**Using AOP for one isolated call** may be harder to follow than an explicit call. AOP serves cross-cutting concerns applied consistently, but requires understanding join points, advice ordering, proxies, and self-invocation limitations.

**Using an event bus for every call inside one transaction** can obscure completion, failure, and commit timing. Events suit independent subscribers or asynchronous workflows; they do not automatically provide exactly-once semantics or transactions.

Evaluate these cases by **operational goals and domain boundaries**, not because a framework provides the feature.

## 14. Design self-assessment exercise

Suppose a class-scheduling application requires:

- Every class has `startTime`, `endTime`, and `teacherId`.
- `endTime` must be after `startTime`.
- Initially, each created schedule represents one session under one counting rule.
- Later, verified requirements add weekly recurring and special sessions.
- The new cases have distinct validation rules.

**Exercises:**

1. Implement a `record ClassSession` or simple immutable class with validation and no Factory initially.
2. Test start/end times, equality boundaries, and null input.
3. Design a second version when recurring schedules appear: first try a small, well-named API; consider Strategy or specialized domain types if policies diverge.
4. Draw before/after dependency diagrams showing where changing rules belong.
5. Compare a `switch` with an interface: which better supports testing new schedule types, limiting unrelated edits, and readability?
6. Identify abstractions that merely forward calls without protecting contracts; try removing them.
7. Explain why **two schedule types sharing some similar code** does not prove they need a common superclass.

**Success criteria:** meets current requirements; no pointless navigation or factories; tested invariants; every new abstraction has a concrete reason; new changes preserve existing behavior.

## 15. Conclusion: good abstractions must earn their keep

A design pattern matters when it makes the system **more correct, readable, testable, or safer to change** in a particular context. Premature design turns uncertain predictions into contracts that must be maintained.

**Useful approach:** start simply, name concepts in domain language, preserve invariants and tests, then observe actual change and extract **the smallest abstraction addressing the real variation**. Neither minimizing class count nor maximizing pattern count is the goal. Optimize how easily people can understand and safely change a working system.
