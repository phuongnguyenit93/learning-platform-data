# Consolidating or Removing Unnecessary Abstractions in OOP

> **Topic:** Refactoring — simplifying Java design by consolidating intermediary classes, interfaces, or methods that no longer have clear responsibilities while preserving the behavior clients rely on.

Good OOP design is not measured by **the number of interfaces, classes, or patterns**. An abstraction is useful when it names a meaningful concept, hides variation, protects responsibility boundaries, or supports genuinely needed substitution.

When a class merely forwards all calls, an interface duplicates an implementation's API without providing a distinct contract, or a hierarchy exists only for speculative future features, the system can become harder to understand. Removing these layers may involve **Inline Class**, **Remove Middle Man**, **Collapse Hierarchy**, or **Inline Method**, depending on the structure being simplified.

**Important:** Not every interface with one implementation is redundant. A single-implementation interface may still define an **I/O boundary**, library contract, plugin mechanism, or architecturally necessary substitution point. Evaluate its purpose and real change costs before deleting it.

## 1. Learning Objectives

After this lesson, you should be able to:

- Distinguish **valuable abstractions** from **forwarding layers that add no value**.
- Recognize `Middle Man`, `Speculative Generality`, redundant hierarchies, forwarding-only wrappers, and excessively extracted methods.
- Choose `Inline Class`, `Remove Middle Man`, `Collapse Hierarchy`, `Inline Method`, or parameter/adapter simplification appropriately.
- Refactor incrementally and validate outcomes with **regression/contract tests**.
- Assess risks involving published APIs, DI containers, frameworks, serialization, or actual extension needs that depend on abstractions.
- Recognize when to **retain an interface** despite currently having just one implementation.

## 2. What Problem Does a Valuable Abstraction Solve?

Consider a payment system with an interface:

~~~java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

The application may currently use one payment gateway, but `PaymentGateway` can still be worth keeping if it separates business code from the provider, defines failure contracts, establishes a network I/O boundary, or permits sandbox testing.

By contrast:

~~~java
interface GreetingPort {
    String greeting(String name);
}

final class GreetingPortImpl implements GreetingPort {
    private final GreetingEngine engine = new GreetingEngine();

    @Override
    public String greeting(String name) {
        return engine.greeting(name); // không có logic, chính sách hoặc hợp đồng riêng
    }
}

final class GreetingEngine {
    String greeting(String name) {
        return "Xin chào, " + name;
    }
}
~~~

If `GreetingPort` and `GreetingPortImpl` are used internally in one place, do not form a stable API, have no genuine substitution need, and serve no architectural boundary, they could be simplified to:

~~~java
final class Greeter {
    String greeting(String name) {
        return "Xin chào, " + name;
    }
}
~~~

This is a **conditional example**. If `GreetingPort` is used by a public library, DI module, plugin, or external client, removing it may break compilation or compatibility. First inspect the API's real consumers.

| Question | Reasons to retain | Reasons to consolidate |
|---|---|---|
| Are there **multiple valid behaviors** to substitute? | Real Strategy/plugin/adapter choices | One path with no requested variants |
| Is there an **infrastructure boundary**? | APIs, databases, networks, message brokers, time, file systems | Pure forwarding wrappers within one module |
| Does the abstraction define an **independent contract**? | Distinct behavior, error, permission, or invariant guarantees | Same signatures and semantics as the wrapped class |
| Does it **reduce coupling**? | Domain code need not know frameworks/vendors | Readers traverse extra files without any coupling reduction |
| Are there **external clients**? | Published, serialized, reflected, or type-name-based DI usage | Only private/internal call sites that can change together |
| Are there **independent reasons to change**? | The classes evolve separately | Both always change together without forming a useful boundary |
| Is there a **real testing benefit**? | Isolated external side effects and independent contract tests | Mocking a forwarding class and duplicating the same tests |

**Do not use rigid rules** such as "one implementation means delete the interface," "merge every class shorter than 20 lines," or "all delegates are redundant." An abstraction's value lies in responsibility and contract stability.

## 3. Common Signs of Excessive Abstraction

### Middle Man — An Intermediary That Mostly Delegates

~~~java
final class OrderFacade {
    private final OrderService service;

    OrderFacade(OrderService service) {
        this.service = service;
    }

    long total(Order order) {
        return service.total(order);
    }
}
~~~

If a facade adds no API meaning, authorization checks, multi-collaborator coordination, exception translation, or stable boundary, clients may call `OrderService` directly. However, a facade is valuable when it represents a **use case** or hides real complexity.

### Speculative Generality — Preparing for an Imaginary Future

For example, adding `AbstractReportFactoryBuilderBase`, `ReportFactoryProvider`, and three interface layers solely because "more formats may be added later" can complicate onboarding and debugging when only one report type exists and no changes are required.

### Fragmented Responsibility — Many Classes Sharing One Small Job

A chain such as `TaxInputWrapper → TaxCalculatorFacade → TaxCalculatorImpl` may merely pass the same two parameters and return one integer. Without a meaningful reason for separation, moving logic into the class that clearly owns the responsibility shortens the path.

### Hierarchies Without Meaningful Polymorphism

~~~java
class BaseOrderPrinter {
    String format(Order order) {
        return order.toString();
    }
}
final class DefaultOrderPrinter extends BaseOrderPrinter { }
~~~

If a subclass adds no behavior, has no extension contract, and exists only to introduce another class name, consider removing that inheritance level after checking dependent clients.

### Tiny Methods That Do Not Clarify Intent

~~~java
long add(long a, long b) { return a + b; }
long sum(long a, long b) { return add(a, b); }
~~~

A method that only calls another method may be worth inlining. However, names such as `taxableAmount` and `validateAccess` can express **domain meaning** or a centralized control point, making them valuable even when short.

## 4. Runnable Java Example: Removing Two Unnecessary Forwarding Layers

**Context:** A checkout service calculates shipping fees and discounts. The legacy code has three layers:

1. `CheckoutFacade` only delegates `quote`.
2. `PricingAdapter` implements `PricingPort` but only calls `PricingEngine`.
3. `PricingEngine` actually validates inputs and calculates prices.

In this example, neither intermediary introduces network/database/plugin boundaries or additional policies. The internal system has one client of the `Checkout` API. Keep that abstraction as **the client-facing contract**, but replace the internal forwarding chain with `SimplifiedCheckout` performing the business logic directly.

### Contract to Preserve

- `subtotalCents` is an amount in cents from `0` through `1_000_000`, inclusive.
- VIP customers receive a **10%** discount (`subtotal / 10`, rounded down) and free shipping.
- Standard customers receive no discount. Orders of **100.000 cents or more** ship free; below that, shipping costs **15.000 cents**.
- `totalCents = subtotalCents - discountCents + shippingCents`.
- Out-of-range inputs throw `IllegalArgumentException`.
- Quoting has no side effects and returns stable results for the same input.

Create `AbstractionRemovalDemo.java` with JDK **17 or later**:

~~~java
import java.util.List;
import java.util.Random;

public class AbstractionRemovalDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;
    private static final long FREE_SHIPPING_AT = 100_000L;
    private static final long SHIPPING_FEE = 15_000L;

    // Hợp đồng công khai với client trong ví dụ.
    interface Checkout {
        Invoice quote(long subtotalCents, boolean vip);
    }

    // Record: so sánh giá trị bằng equals(), không cần setter.
    record Invoice(long discountCents, long shippingCents, long totalCents) {}

    private static void validate(long subtotalCents) {
        if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
            throw new IllegalArgumentException("Invalid subtotalCents");
        }
    }

    // BEFORE: một interface nội bộ không có biến thể thực tế.
    interface PricingPort {
        Invoice calculate(long subtotalCents, boolean vip);
    }

    // Lớp chứa logic nghiệp vụ ở thiết kế cũ.
    static final class PricingEngine {
        Invoice calculate(long subtotalCents, boolean vip) {
            validate(subtotalCents);
            long discount = vip ? subtotalCents / 10 : 0;
            long shipping = (vip || subtotalCents >= FREE_SHIPPING_AT)
                ? 0 : SHIPPING_FEE;
            return new Invoice(
                discount, shipping, subtotalCents - discount + shipping
            );
        }
    }

    // Chỉ chuyển tiếp, không chuyển đổi dữ liệu/hợp đồng/ngoại lệ.
    static final class PricingAdapter implements PricingPort {
        private final PricingEngine engine = new PricingEngine();

        @Override
        public Invoice calculate(long subtotalCents, boolean vip) {
            return engine.calculate(subtotalCents, vip);
        }
    }

    // Facade này cũng chỉ forward vào adapter.
    static final class LegacyCheckout implements Checkout {
        private final PricingPort port = new PricingAdapter();

        @Override
        public Invoice quote(long subtotalCents, boolean vip) {
            return port.calculate(subtotalCents, vip);
        }
    }

    // AFTER: gộp logic nội bộ vào class thực hiện use case.
    // Hợp đồng Checkout mà client sử dụng không đổi.
    static final class SimplifiedCheckout implements Checkout {
        @Override
        public Invoice quote(long subtotalCents, boolean vip) {
            validate(subtotalCents);
            long discount = vip ? subtotalCents / 10 : 0;
            long shipping = (vip || subtotalCents >= FREE_SHIPPING_AT)
                ? 0 : SHIPPING_FEE;
            return new Invoice(
                discount, shipping, subtotalCents - discount + shipping
            );
        }
    }

    record Case(long subtotal, boolean vip, Invoice expected) {}

    // Oracle độc lập: expected value được ghi rõ theo yêu cầu.
    private static final List<Case> CASES = List.of(
        new Case(0, false, new Invoice(0, 15_000, 15_000)),
        new Case(0, true, new Invoice(0, 0, 0)),
        new Case(99_999, false, new Invoice(0, 15_000, 114_999)),
        new Case(100_000, false, new Invoice(0, 0, 100_000)),
        new Case(100_001, false, new Invoice(0, 0, 100_001)),
        new Case(250_001, true, new Invoice(25_000, 0, 225_001)),
        new Case(1_000_000, true, new Invoice(100_000, 0, 900_000))
    );

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    // Bộ regression test áp cho bất kỳ implementation của Checkout.
    static void verifyContract(String label, Checkout service) {
        for (Case c : CASES) {
            Invoice actual = service.quote(c.subtotal(), c.vip());
            require(c.expected().equals(actual),
                label + " differs at " + c + "; actual=" + actual);

            require(actual.discountCents() >= 0,
                label + ": negative discount");
            require(actual.totalCents() ==
                    c.subtotal() - actual.discountCents()
                        + actual.shippingCents(),
                label + ": invalid total");
        }

        expectInvalid(() -> service.quote(-1, false));
        expectInvalid(() -> service.quote(MAX_SUBTOTAL + 1, true));
    }

    private static void expectInvalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    // Differential test dùng nhiều input cố định seed.
    static void compareBeforeAfter(Checkout before, Checkout after) {
        Random random = new Random(219L);
        for (int i = 0; i < 1_000; i++) {
            long subtotal = random.nextInt(1_000_001);
            boolean vip = random.nextBoolean();
            Invoice oldResult = before.quote(subtotal, vip);
            Invoice newResult = after.quote(subtotal, vip);
            require(oldResult.equals(newResult),
                "Behavior changed for subtotal=" + subtotal + ", vip=" + vip);
        }
    }

    public static void main(String[] args) {
        Checkout oldDesign = new LegacyCheckout();
        Checkout newDesign = new SimplifiedCheckout();

        verifyContract("legacy", oldDesign);
        verifyContract("simplified", newDesign);
        compareBeforeAfter(oldDesign, newDesign);

        System.out.println("PASS: legacy contract");
        System.out.println("PASS: simplified contract");
        System.out.println("PASS: before/after comparison");
        System.out.println(newDesign.quote(250_001, true));
    }
}
~~~

Compile and run:

~~~bash
javac AbstractionRemovalDemo.java
java AbstractionRemovalDemo
~~~

Expected output:

~~~text
PASS: legacy contract
PASS: simplified contract
PASS: before/after comparison
Invoice[discountCents=25000, shippingCents=0, totalCents=225001]
~~~

The old and new classes coexist **only for demonstration and comparison in the demo file**. In a real project, after validation and migrating all call sites, remove unused `PricingPort`, `PricingAdapter`, `PricingEngine`, and `LegacyCheckout` layers. Do not maintain parallel production paths without a specific compatibility or migration reason.

### Before and After Refactoring

~~~mermaid
flowchart LR
    subgraph Before["Trước: bốn lớp/interface trên đường gọi"]
      A["Client"] --> B["Checkout"]
      B --> C["LegacyCheckout"]
      C --> D["PricingPort"]
      D --> E["PricingAdapter"]
      E --> F["PricingEngine"]
    end
    subgraph After["Sau: một hợp đồng và một implementation"]
      G["Client"] --> H["Checkout"]
      H --> I["SimplifiedCheckout"]
    end
~~~

The improvement is a **clearer execution path**: readers no longer open multiple classes to find where pricing is calculated. Calls through `Checkout`, the returned `Invoice` type, and input/output rules remain unchanged.

## 5. Choosing the Right Consolidation or Removal Technique

| Technique | When to use it | Example | Risks to check |
|---|---|---|---|
| **Inline Method** | A method only calls another and adds no meaning | `int calc() { return addTax(); }` adds no contract | The method name may encode useful domain language |
| **Inline Class** | A class does too little and has no distinct responsibility | `AddressFormatterHelper` used only by `AddressFormatter` | Frameworks or external clients may reference the class |
| **Remove Middle Man** | A class mostly consists of pure delegation | `Facade → Adapter → Engine` forwarding chain | Delegates may protect security, transaction, or I/O boundaries |
| **Collapse Hierarchy** | Superclass/subclass differ little in behavior/responsibility | `DefaultPrinter extends BasePrinter` without extra logic | Polymorphic behavior, binary/source compatibility, overrides |
| **Remove Unused Abstraction** | An interface/abstract class/factory has no remaining legitimate consumers | An interface only for a removed feature | Plugins, reflection, DI configuration, external clients |
| **Simplify Parameter Object** | An object only wraps a value without invariants or distinct meaning | `NameWrapper` with no policies or reuse | Could be a value object protecting units/validation |
| **Replace Hierarchy with Composition** | Complex inheritance only reuses a few behaviors | Many subclasses combining two dimensions of variation | Does not always **reduce** abstraction; assess separately |

**Do not merge independent responsibilities just to reduce file counts.** If `PricingEngine` serves multiple use cases or has its own responsibility, retain it and remove only the redundant adapter. Simplify in ways that improve *cohesion*, do not worsen *coupling*, and keep testing straightforward.

## 6. How Do Inline Class and Collapse Hierarchy Differ?

### Inline Class: Return a Small Responsibility to Its Proper Owner

Suppose:

~~~java
final class NameJoiner {
    String fullName(String first, String last) {
        return first + " " + last;
    }
}

final class CustomerLabel {
    private final NameJoiner joiner = new NameJoiner();

    String label(String first, String last) {
        return joiner.fullName(first, last);
    }
}
~~~

If `NameJoiner` has only this one caller, is not reused, has no I/O dependency, and does not encapsulate a shared formatting rule, it could be inlined:

~~~java
final class CustomerLabel {
    String label(String first, String last) {
        return first + " " + last;
    }
}
~~~

But if the entire system must follow localized name-display rules, independent formatting is an important responsibility. In that case, retain a service/type expressing the proper contract.

### Collapse Hierarchy: Remove an Inheritance Level Without Distinction

Before:

~~~java
class BaseFormatter {
    String format(int value) {
        return Integer.toString(value);
    }
}

final class DefaultFormatter extends BaseFormatter {
    // Không override, không thêm trạng thái hoặc invariant.
}
~~~

If no consumer needs to distinguish `BaseFormatter` from `DefaultFormatter`, they can be replaced by one class:

~~~java
final class Formatter {
    String format(int value) {
        return Integer.toString(value);
    }
}
~~~

This does not mean every empty subclass must disappear: a subclass might be a **marker type**, discovered through framework annotations, preserve a compatibility contract, or have a confirmed upcoming extension requirement. Inspect clients, annotations, and configuration before changing the hierarchy.

## 7. Identify Real Boundaries Before Deleting Abstractions

Similar-looking forwarding layers may serve very different purposes:

~~~java
interface Clock {
    java.time.Instant now();
}
~~~

This may be a useful boundary for testing time-dependent behavior without waiting for the real clock. If `Clock` isolates domain logic from the system clock, removing it can make testing harder.

~~~java
interface CustomerRepository {
    Customer findById(long id);
}
~~~

This may be a boundary between **domain/application** and **database**, even with just one JDBC implementation. Removing the interface could pull SQL/infrastructure into code that should not depend on it.

By contrast:

~~~java
final class IdEchoAdapter {
    long pass(long id) {
        return id;
    }
}
~~~

If this is merely a meaningless layer with no validation, transformation, boundary, or semantics, there is no clear architectural reason to retain it.

**Quick Decision Table:**

| Boundary type | Retain when… | Consider consolidating when… |
|---|---|---|
| Domain ↔ database/network | Hides side effects, permits infrastructure substitution and stable tests | An intermediary merely renames methods and the contract already lives elsewhere |
| Use case ↔ domain | Coordinates transactions, authorization, or several collaborators | A use case simply forwards without distinct meaning |
| API ↔ DTO/domain | Handles validation, versioning, mapping, or serialization | A wrapper performs no conversion and is not a public API |
| Strategy/Plugin | Real variants or an extension contract exist | Only a speculative future with no consumers |
| Value object | Enforces units, constraints, or domain meaning | A wrapper only renames a primitive without semantics |
| Module facade | Hides several subsystems and stabilizes APIs | The facade forwards 100% of calls without hiding details |

## 8. Safe Refactoring: Remove Redundancy While Preserving Contracts

1. **Map the current call path.** Draw or trace calls from the public API to the business rules. Mark forwarding-only classes/interfaces and identify their clients.
2. **Find the reason for each layer.** Inspect dependencies, tests, DI configuration, annotations, visibility, framework integration, and extension points. Mark boundaries worth keeping.
3. **Establish public behavior.** Write specification-based tests for valid inputs, boundaries, exceptions, outputs, and side effects, incorporating special cases from real defects.
4. **Choose a small transformation.** Remove one delegate before considering whether to merge an engine; do not delete a whole hierarchy in one large commit.
5. **Migrate call sites consistently.** Invoke the surviving abstraction directly, retain API names that must stay stable, and prevent old and new paths from diverging.
6. **Run compiler, unit, regression, and integration tests.** For DI/reflection, verify application startup, bean configuration, serialization, and runtime routing.
7. **Measure actual impact.** Evaluate steps needed to locate logic, classes edited for new requirements, testability, and review clarity. Removing a redundant layer can be more valuable than reducing line counts.
8. **Clean dead code.** Once consumers are absent, remove obsolete imports, classes, interfaces, configuration, and implementation-detail tests while retaining behavioral tests.

~~~mermaid
flowchart TD
    A["Tìm các tầng chỉ forward hoặc hierarchy thừa"] --> B["Xác định client và vai trò contract"]
    B --> C{"Có ranh giới/biến thể/lợi ích thật?"}
    C -->|Có| D["Giữ abstraction, cải thiện naming/API nếu cần"]
    C -->|Không| E["Chốt test hành vi và điểm tương thích"]
    E --> F["Inline/gộp một tầng"]
    F --> G["Chạy compile + regression/integration tests"]
    G --> H{"Hợp đồng và client còn đúng?"}
    H -->|Không| I["Sửa hoặc hoàn tác bước refactor"]
    I --> G
    H -->|Có| J["Xóa đường đi dư, review thiết kế"]
~~~

### Sequence When External Clients Use the Public API

If `PricingPort` is public in a library, immediately changing client calls may be a **breaking change**. A safer approach is:

- Keep a **compatibility adapter** during migration and mark it `@Deprecated` when appropriate.
- Publish the new API, document migration, and update known call sites.
- Check source/binary compatibility and release versions; remove old APIs only in a release allowing breaking changes.
- Verify whether DI configuration, plugins, reflection, and serialized data reference old type names.

In an internal application built as a unit, all call sites may be migrated more directly, but tests and runtime checks are still required.

## 9. Testing Refactoring Correctness

When **the goal is design change rather than functional change**, tests should focus on *client-observable outcomes* instead of class or method counts.

| Test category | Example | What it protects |
|---|---|---|
| Specification test | `quote(100_000, false)` qualifies for free shipping | Business correctness independently of old code |
| Boundary test | 0; 99.999; 100.000; 100.001; 1.000.000 | No branch/condition is lost during inlining |
| Negative test | -1; 1.000.001 | Validation and error types remain correct |
| Differential test | 1.000 random inputs with a fixed seed | Detect differences between old and new paths |
| Side-effect test | No extra I/O/charges beyond the contract | Removing intermediaries adds no side effects |
| Integration test | Start DI and invoke the API through the transport | Type removal does not break wiring/runtime |
| Client compilation | Compile dependent modules, if any | Avoid unintentional public-signature breakage |
| Performance check | Measure affected flows when SLAs exist | Consolidation adds no unnecessary computation/I/O |

### JUnit 5 Example

If the project declares `org.junit.jupiter:junit-jupiter` and tests reside in the same package as the demo class, add `CheckoutRefactoringTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CheckoutRefactoringTest {
    @Test
    void simplifiedImplementationKeepsBusinessContract() {
        var checkout = new AbstractionRemovalDemo.SimplifiedCheckout();

        assertEquals(
            new AbstractionRemovalDemo.Invoice(0, 0, 100_000),
            checkout.quote(100_000, false)
        );
        assertEquals(
            new AbstractionRemovalDemo.Invoice(25_000, 0, 225_001),
            checkout.quote(250_001, true)
        );
    }

    @Test
    void invalidInputsStillFail() {
        var checkout = new AbstractionRemovalDemo.SimplifiedCheckout();

        assertThrows(IllegalArgumentException.class,
            () -> checkout.quote(-1, false));
        assertThrows(IllegalArgumentException.class,
            () -> checkout.quote(1_000_001, true));
    }

    @Test
    void oldAndNewMatchOnRepresentativeCases() {
        AbstractionRemovalDemo.Checkout oldService =
            new AbstractionRemovalDemo.LegacyCheckout();
        AbstractionRemovalDemo.Checkout newService =
            new AbstractionRemovalDemo.SimplifiedCheckout();

        AbstractionRemovalDemo.verifyContract("old", oldService);
        AbstractionRemovalDemo.verifyContract("new", newService);
        AbstractionRemovalDemo.compareBeforeAfter(oldService, newService);
    }
}
~~~

Demo nested types have package-private access, so place tests in the same package. Production code should organize types and visibility according to the application's architecture.

**Do not rely solely on comparing old and new versions.** If the old version was already wrong, faithfully preserving its defect can still pass differential tests. Expected `Invoice` values in the demo are written **directly from the requirements** as an independent oracle.

## 10. Common Mistakes

**Deleting an interface simply because it has one implementation.** Implementation count is not a complete measure of value. An abstraction at a database, I/O, clock, or payment-gateway boundary may be important for protecting domain code.

**Merging classes based on line counts.** Two 10-line classes should remain separate if they have **independent reasons to change**. Conversely, a chain of 100-line classes doing nothing but forwarding may need simplification.

**Moving everything into a "God Class."** The objective is not to minimize classes at any cost. If consolidation leaves a class with unrelated responsibilities, maintainability deteriorates.

**Refactoring while changing business rules.** If totals change due to a new pricing policy, that is a functional change that must be documented separately. A refactoring preserves behavior only when the contract is verified unchanged.

**Neglecting reflection, DI, or APIs outside the module.** Code may compile but fail at runtime because bean names, annotations, constructor injection, or configuration referenced a removed class.

**Testing only structural details.** A test asserting that `PricingAdapter.calculate()` was called once becomes meaningless after removing `PricingAdapter`. Replace it with tests for `Checkout.quote()` and genuinely relevant side effects.

**Inlining methods by duplicating logic across clients.** Removing a shared method and copying its body into many callers can create `Duplicate Code` and increase change costs. Inline only when the logic belongs to the caller and does not scatter a common rule.

**Ignoring type and visibility constraints.** Moving methods between classes may expose private fields, broaden access, or affect overloads/generics. Use the compiler, tests, and access-modifier reviews.

## 11. Practice Exercises

**Exercise 1 — Classify:** Given `UserRepository` (DB contract), `UserRepositoryImpl` (real SQL), `UserRepositoryProxy` (forwarding only), and `UserService` (business logic), identify the likely middle man. Specify **evidence to verify** before removing it.

**Exercise 2 — Inline Class:** A `NamePrinter` used only by `GreetingService` joins names without any shared formatting rule. Rewrite the code without the helper class. Test normal, empty, and `null` inputs according to the current contract.

**Exercise 3 — Collapse Hierarchy:** `DefaultDiscountCalculator extends DiscountCalculator` but overrides nothing, and no client uses the subclass as a marker. Redesign it as one class and predict effects on constructors and `import` statements.

**Exercise 4 — Scoped Refactoring:** In `AbstractionRemovalDemo`, try removing only `PricingAdapter` while retaining `PricingEngine` if another use case reuses it. Assess whether the remaining class has a clearer responsibility.

**Exercise 5 — Boundary Defect:** Deliberately change `subtotalCents >= FREE_SHIPPING_AT` to `subtotalCents > FREE_SHIPPING_AT` in `SimplifiedCheckout`. Run regression tests, identify exactly which case detects the bug, and restore the correct condition.

**Exercise 6 — Real Review:** Find a long call chain in an application. Diagram it, marking which layers provide contracts, validation, transactions, authorization, I/O, mapping, or mere forwarding. Propose removing **at least one demonstrably redundant layer**, write behavioral tests first, and record the results after testing.

## 12. Completion Criteria

Before removing an abstraction, you should be able to answer three questions:

1. **What does it protect?** A contract, dependency boundary, real variant, or merely a forwarding call?
2. **What will consolidation improve?** Fewer steps to locate logic, fewer edit points, clearer responsibilities, or easier testing without new coupling?
3. **How do we know the refactoring is safe?** Specification, boundary, and exception tests plus checks of affected clients/APIs demonstrate that public behavior remains correct.

When evidence supports all three, **consolidating or removing unnecessary abstractions** makes OOP design more direct without sacrificing clarity or genuine extensibility.
