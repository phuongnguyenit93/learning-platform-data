# Strategy Pattern in Java: Replacing Algorithms Through Composition

> **Topic:** OOP → Design Patterns → Strategy and interchangeable algorithms.  
> **Objective:** Understand why Strategy is useful, identify the Context–Strategy–Concrete Strategy roles, implement it in Java, select algorithms at runtime, test their shared contract, and recognize when extra abstraction is unnecessary.

## 1. What Is Strategy?

**Strategy** is a *behavioral design pattern* in the GoF catalog. The idea is to **encapsulate interchangeable algorithms as objects sharing the same contract**, then let the object using the algorithm (Context) work through that contract.

When processing needs to change, the Context receives another implementation instead of embedding detailed `if/else` or `switch` branches. An interchangeable algorithm might calculate fees, choose shipping routes, sort data, apply promotions, authenticate users, compress data, or assign scores.

Three core roles:

| Role | Responsibility | Used in this example |
|---|---|---|
| **Strategy** | Defines the shared operation and input/output contract | `DiscountStrategy` |
| **Concrete Strategy** | Implements one algorithm variant | `NoDiscount`, `PercentageDiscount`, `FixedDiscount` |
| **Context** | Coordinates business logic and invokes Strategy through its interface | `Checkout` |
| **Client / composition root** | Selects the appropriate Strategy for the context and supplies it | `StrategyDemo.main` |

**Core point:** Context does not need to know how a concrete algorithm is implemented. It relies solely on the behavior guaranteed by Strategy.

## 2. The Problem Before Introducing Strategy

An online store may support three discount policies: none, percentage-based, and fixed amount. If the algorithms are embedded directly in Checkout:

~~~java
// Minh họa mã khó mở rộng — không phải chương trình hoàn chỉnh.
BigDecimal calculateDiscount(String type, BigDecimal subtotal) {
    if ("NONE".equals(type)) {
        return BigDecimal.ZERO;
    }
    if ("PERCENT".equals(type)) {
        return subtotal.multiply(new BigDecimal("0.10"));
    }
    if ("FIXED".equals(type)) {
        return new BigDecimal("30.00").min(subtotal);
    }
    throw new IllegalArgumentException("Unknown discount type");
}
~~~

The example is deliberately simplified and **does not yet handle monetary rounding**. Design problems arise as algorithms, configuration values, and rules proliferate:

- Each new policy requires changing the method serving the main business operation.
- Variants mix selection conditions with calculation formulas, making existing branches easy to modify accidentally.
- Testing each algorithm independently becomes difficult when everything lives in one large method.
- If several screens or use cases calculate discounts, the branches may be duplicated.

This does not mean `if/else` is always wrong. For **two short, stable conditions with no independent change requirements**, a simple function may be clearer than several classes. Strategy helps when **the algorithm is truly an independent axis of variation**.

## 3. Strategy Structure

~~~mermaid
classDiagram
    class DiscountStrategy {
        <<interface>>
        +discountFor(subtotal) BigDecimal
    }
    class NoDiscount {
        +discountFor(subtotal) BigDecimal
    }
    class PercentageDiscount {
        -rate : BigDecimal
        +discountFor(subtotal) BigDecimal
    }
    class FixedDiscount {
        -amount : BigDecimal
        +discountFor(subtotal) BigDecimal
    }
    class Checkout {
        -strategy : DiscountStrategy
        +Checkout(strategy)
        +quote(subtotal) PriceQuote
    }
    class StrategyDemo {
        +main(args) void
    }

    DiscountStrategy <|.. NoDiscount
    DiscountStrategy <|.. PercentageDiscount
    DiscountStrategy <|.. FixedDiscount
    Checkout --> DiscountStrategy : sử dụng
    StrategyDemo ..> Checkout : khởi tạo
    StrategyDemo ..> DiscountStrategy : lựa chọn
~~~

The important arrow is **`Checkout → DiscountStrategy`**: the Context depends on an abstraction. New Concrete Strategies can be added without rewriting the Context's orchestration formula.

Strategy usually uses **composition**: the Context **has a** Strategy object. This favors composition over creating multiple Context subclasses; it does not prohibit inheritance in every situation.

## 4. Standalone Java 17 Example: Discount Strategies

Define a clear contract before writing implementations:

- `subtotal` is nonnegative money represented **to the cent** (up to two meaningful decimal places; additional trailing zeros are allowed).
- `discountFor(subtotal)` returns a non-null, **nonnegative amount no greater than subtotal**, with at most two meaningful decimal places.
- Strategy **does not modify subtotal**, initiate payments, or create side effects beyond calculation. `BigDecimal` itself is immutable.
- Context validates the input amount and rejects results that violate the contract so algorithm errors are detected near their source.

> This is a two-decimal-place monetary model for teaching Strategy. Real products need business-defined currencies, smallest units, taxes, rounding rules, and promotion scopes; not all currencies have two fractional digits.

Save the full example as **`StrategyDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.Objects;

// Strategy: một thuật toán giảm giá, không thực hiện thanh toán.
@FunctionalInterface
interface DiscountStrategy {
    /**
     * Tiền điều kiện: subtotal không null, >= 0, chính xác tới 2 số lẻ.
     * Hậu điều kiện: 0 <= kết quả <= subtotal; tối đa 2 số lẻ.
     */
    BigDecimal discountFor(BigDecimal subtotal);
}

// Concrete Strategy A: không giảm.
final class NoDiscount implements DiscountStrategy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return new BigDecimal("0.00");
    }
}

// Concrete Strategy B: giảm theo tỷ lệ.
// Ví dụ: rate = 0.10 tương ứng 10%.
final class PercentageDiscount implements DiscountStrategy {
    private final BigDecimal rate;

    PercentageDiscount(BigDecimal rate) {
        Objects.requireNonNull(rate, "rate");
        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("rate must be in [0, 1]");
        }
        this.rate = rate;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(rate)
                .setScale(2, RoundingMode.HALF_UP);
    }
}

// Concrete Strategy C: giảm số tiền cố định, không vượt subtotal.
final class FixedDiscount implements DiscountStrategy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }
        try {
            this.amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException("amount has fractions of cent", ex);
        }
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return amount.min(subtotal);
    }
}

// Giá trước giảm, mức giảm và giá cuối cùng là một kết quả bất biến.
record PriceQuote(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal total
) {}

// Context: giữ quy trình báo giá, ủy quyền công thức cho Strategy.
final class Checkout {
    private final DiscountStrategy strategy;

    Checkout(DiscountStrategy strategy) {
        this.strategy = Objects.requireNonNull(strategy, "strategy");
    }

    PriceQuote quote(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }

        final BigDecimal normalized;
        try {
            normalized = subtotal.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "subtotal has fractions of cent", ex);
        }

        BigDecimal rawDiscount = Objects.requireNonNull(
                strategy.discountFor(normalized),
                "Strategy must return a discount");

        final BigDecimal discount;
        try {
            discount = rawDiscount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalStateException(
                    "Strategy returned fractions of cent", ex);
        }

        if (discount.signum() < 0
                || discount.compareTo(normalized) > 0) {
            throw new IllegalStateException(
                    "Strategy must return discount in [0, subtotal]");
        }

        return new PriceQuote(
                normalized,
                discount,
                normalized.subtract(discount));
    }
}

public class StrategyDemo {
    public static void main(String[] args) {
        // Đây là nơi cấu hình/chọn chiến lược theo tên.
        Map<String, DiscountStrategy> strategies = Map.of(
                "NONE", new NoDiscount(),
                "TEN_PERCENT",
                    new PercentageDiscount(new BigDecimal("0.10")),
                "FIXED_30",
                    new FixedDiscount(new BigDecimal("30.00"))
        );

        BigDecimal subtotal = new BigDecimal("120.00");

        for (String key : List.of("NONE", "TEN_PERCENT", "FIXED_30")) {
            DiscountStrategy selected = strategies.get(key);
            Checkout checkout = new Checkout(selected);
            PriceQuote quote = checkout.quote(subtotal);

            System.out.println(
                    key + " -> discount=" + quote.discount()
                    + ", total=" + quote.total());
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac StrategyDemo.java
java StrategyDemo
~~~

Expected output:

~~~text
NONE -> discount=0.00, total=120.00
TEN_PERCENT -> discount=12.00, total=108.00
FIXED_30 -> discount=30.00, total=90.00
~~~

**Reading the example component by component:**

1. `DiscountStrategy` is a **unified contract** that specifies “calculate a discount” without prescribing an algorithm.
2. `NoDiscount`, `PercentageDiscount`, and `FixedDiscount` implement independent algorithms.
3. `Checkout` receives a Strategy through **constructor injection**. It validates shared rules and calls `strategy.discountFor(...)`. It never uses `instanceof` or depends on concrete class names.
4. `StrategyDemo.main` selects a strategy from a `Map`, constructs the Context, and runs the same workflow. This demonstrates **runtime algorithm selection** before Context creation.
5. For a new policy such as `LoyaltyDiscount`, add a class implementing `DiscountStrategy` and register it at the selection point; most `Checkout` code remains unchanged.

Note that `Map` is merely a **mechanism for selecting** a Strategy. A Map/Registry does not define Strategy; what defines it is **supplying an algorithm with a shared contract to a Context** through a common interface.

## 5. When Can Strategy Change?

In the GoF description, a Strategy may be chosen when creating the Context or replaced with a different implementation as needed. Two common approaches and an additional per-call option are:

| Approach | Illustration | Appropriate when |
|---|---|---|
| **Select when creating Context (immutable)** | `new Checkout(new PercentageDiscount(rate))` | Each request/session has its own policy; concurrency is easier to control |
| **Change Strategy within Context** | `context.setStrategy(other)` | A long-lived object deliberately switches algorithms with explicit state management |
| **Pass Strategy to each method** | `quote(subtotal, strategy)` | One Context handles many independent requests, with algorithms as per-call arguments |

Example of switching Strategy directly (separate from the earlier `Checkout` class):

~~~java
// Chỉ minh họa cơ chế thay đổi động trên một Context.
final class MutableQuoteService {
    private DiscountStrategy strategy;

    MutableQuoteService(DiscountStrategy initial) {
        setStrategy(initial);
    }

    void setStrategy(DiscountStrategy next) {
        strategy = Objects.requireNonNull(next);
    }

    BigDecimal calculateDiscount(BigDecimal validSubtotal) {
        return strategy.discountFor(validSubtotal);
    }
}
~~~

When one `MutableQuoteService` is shared by several HTTP requests, calling `setStrategy` for one request may affect another. Do not use a mutable singleton to store user-specific strategy selection without synchronization/race-condition controls. Usually **select a Strategy per request and pass it explicitly**, or use an immutable Context such as `Checkout`.

Note that `MutableQuoteService` intentionally omits monetary contract checks. The full example assigns those checks to `Checkout`; preserve them in real implementations.

## 6. Writing Strategy with Java Lambdas

Because `DiscountStrategy` has **one abstract method** (`@FunctionalInterface`), Java can represent a short algorithm without complex state as a lambda instead of a concrete class.

~~~java
DiscountStrategy weekendDiscount = subtotal ->
        subtotal.multiply(new BigDecimal("0.05"))
                .setScale(2, RoundingMode.HALF_UP);

Checkout checkout = new Checkout(weekendDiscount);
PriceQuote result = checkout.quote(new BigDecimal("200.00"));
// Giảm 10.00, tổng còn 190.00
~~~

These lines use the types/imports already defined in `StrategyDemo.java`; they can go inside `main` or a compatible Java method.

**Choose a dedicated class** when a Strategy has multiple steps, configuration parameters, dependencies (services or repositories), specialized logging, or complex tests. **Choose a lambda** when behavior is short, the variable name is self-explanatory, and business rules remain clear. A lambda is still a `DiscountStrategy` contract implementation.

## 7. Strategy and OOP/SOLID Principles

Strategy clearly illustrates three OOP ideas:

- **Encapsulation:** Each algorithm variant owns its calculation details.
- **Polymorphism:** A call to `discountFor` dispatches to the injected implementation.
- **Composition:** Context holds a Strategy reference without requiring inheritance of Context.

Connections to SOLID:

| Principle | How Strategy helps | Caveat |
|---|---|---|
| **SRP** | Separates checkout orchestration from individual discount calculations | Avoid useless classes for tiny expressions |
| **OCP** | Add `LoyaltyDiscount` without changing the shared `Checkout` algorithm | The composition root still must register/select variants |
| **LSP** | Strategies must actually be substitutable under `0 ≤ discount ≤ subtotal` | Having an interface **does not imply** every implementation is valid |
| **ISP** | One-operation interface sufficient for Context | Avoid bloated interfaces that force unrelated responsibilities on Strategies |
| **DIP** | `Checkout` depends on `DiscountStrategy` rather than a concrete class | Respect dependency direction among packages/modules when separating code |

DI and Strategy are also different: **DI** describes supplying dependencies externally; **Strategy** describes a **family of interchangeable algorithms**. The example uses both by constructor-injecting a Strategy into its Context.

## 8. Testing Strategy Systematically

Algorithm separation enables two levels of tests: (a) each Strategy’s formula, and (b) the common contract and how Context invokes Strategy. The snippets below use JUnit Jupiter (JUnit 5) in the same package as `StrategyDemo.java` under the test source set; they require the project’s `junit-jupiter` dependency and test runner.

### 8.1. Unit-Test Algorithms and Boundary Cases

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class DiscountStrategyTest {
    @Test
    void percentageDiscountRoundsToCents() {
        Checkout checkout = new Checkout(
                new PercentageDiscount(new BigDecimal("0.10")));

        PriceQuote quote = checkout.quote(new BigDecimal("12.34"));

        assertEquals(new BigDecimal("1.23"), quote.discount());
        assertEquals(new BigDecimal("11.11"), quote.total());
    }

    @Test
    void fixedDiscountNeverExceedsSubtotal() {
        Checkout checkout = new Checkout(
                new FixedDiscount(new BigDecimal("30.00")));

        PriceQuote quote = checkout.quote(new BigDecimal("12.00"));

        assertEquals(new BigDecimal("12.00"), quote.discount());
        assertEquals(new BigDecimal("0.00"), quote.total());
    }

    @Test
    void invalidAmountAndBadStrategyAreRejected() {
        Checkout checkout = new Checkout(new NoDiscount());

        assertThrows(IllegalArgumentException.class,
                () -> checkout.quote(new BigDecimal("-1.00")));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.quote(new BigDecimal("1.001")));

        // Một Strategy phá hợp đồng trả mức giảm lớn hơn subtotal.
        DiscountStrategy broken = amount -> amount.add(BigDecimal.ONE);
        Checkout guarded = new Checkout(broken);

        assertThrows(IllegalStateException.class,
                () -> guarded.quote(new BigDecimal("10.00")));
    }
}
~~~

In the test above, `BigDecimal.equals` compares **scale** as well; `1.23` and `1.230` are different under `equals`. The example normalizes values to two decimal places for exact comparisons. If only numeric value matters, use `compareTo`.

### 8.2. Reusable Contract Tests for Every Strategy

Every new Strategy must honor the same contract: valid input, non-null output, nonnegative result, and a discount no greater than the original price. Use `@ParameterizedTest` to avoid duplicating tests when adding variants:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class DiscountStrategyContractTest {
    static Stream<Arguments> strategies() {
        return Stream.of(
                Arguments.of("none", new NoDiscount()),
                Arguments.of("percent",
                        new PercentageDiscount(new BigDecimal("0.10"))),
                Arguments.of("fixed",
                        new FixedDiscount(new BigDecimal("30.00")))
        );
    }

    @ParameterizedTest(name = "{0} preserves discount bounds")
    @MethodSource("strategies")
    void allStrategiesSatisfyContract(
            String name, DiscountStrategy strategy) {
        for (String value : new String[]{"0.00", "0.01", "12.34", "120.00"}) {
            BigDecimal subtotal = new BigDecimal(value);
            BigDecimal discount = assertDoesNotThrow(
                    () -> strategy.discountFor(subtotal));
            assertNotNull(discount);
            assertTrue(discount.compareTo(BigDecimal.ZERO) >= 0);
            assertTrue(discount.compareTo(subtotal) <= 0);
            assertEquals(0, discount.setScale(2,
                    java.math.RoundingMode.UNNECESSARY)
                    .compareTo(discount));
        }
    }
}
~~~

The final assertion checks whether the discount is exactly representable with two decimal places; if a Strategy returns a value with three meaningful fractional digits, `setScale(2, UNNECESSARY)` throws `ArithmeticException` and the test fails. The test requires the additional `junit-jupiter-params` dependency. This is a **sample test suite**, not exhaustive coverage; add property-based tests, extreme values, and specific boundaries (at, just below, and just above thresholds, or large orders).

In production, pricing must be tested alongside **rounding, promotion limits, taxes, and currency rules**. The Strategy contract is where these shared rules should be stated explicitly.

## 9. Comparing Strategy with Similar Patterns and Approaches

| Approach | Main idea | How it differs from Strategy |
|---|---|---|
| **Strategy** | Select an algorithm among implementations sharing a contract | Context delegates behavior to a Strategy object |
| **State** | Behavior depends on the internal state of Context; transitions belong to the model | State objects typically govern **transitions**; Strategies are generally chosen by clients or configuration |
| **Template Method** | A base class fixes the algorithm skeleton, subclasses override steps | Uses **inheritance**, while Strategy primarily uses **composition/delegation** |
| **Command** | Encapsulates a request/action as an object | Often focuses on execution, queues, logs, or undo; Strategy varies an algorithm |
| **Factory Method / Factory** | Creates objects | A Factory may **create or select** a Strategy, while Strategy focuses on behavior |
| **A simple `switch`** | Selects algorithms with direct conditionals | Fewer classes; appropriate when branches are short, few, and rarely change |

A caution: Strategy and State can have **similar UML diagrams** (Context holds an interface with multiple implementations). Distinguish them by **model semantics**: choosing a way to do the same task versus representing object state and transitions.

### When Strategy May Not Be the Best Choice

Do not automatically create an interface and five classes to replace one short addition. Consider:
- Are variants real, or only hypothetical future requirements?
- Is each variant complex enough or independently changeable enough to benefit from a separate class?
- Is the contract stable and easy to express?
- Is the code used only once or shared by multiple Contexts?
- Must variants change at runtime or only at build time?
- Are the costs of classes, registration, configuration, and tests justified?

A pure function or `switch` can still be a good design. Refactor toward Strategy once the variation is evident.

## 10. Advanced: Safely Selecting Strategy from User Data

In the main example, `Map` holds pre-registered, trusted instances. When strategy names come from HTTP requests, configuration files, or databases, **do not** load arbitrary classes from input names via reflection. Map valid keys to explicitly registered/configured Strategies.

Extension of `StrategyDemo.java`:

~~~java
// strategies là Map<String, DiscountStrategy> trong main.
String requested = "TEN_PERCENT"; // Ví dụ giá trị đã đọc từ request.
DiscountStrategy strategy = strategies.get(requested);

if (strategy == null) {
    throw new IllegalArgumentException(
            "Unsupported discount policy: " + requested);
}

PriceQuote quote = new Checkout(strategy)
        .quote(new BigDecimal("200.00"));
System.out.println(quote.total()); // 180.00
~~~

For policies that call a database or external API, a Strategy may be a dedicated class receiving constructor-injected dependencies. Shared Strategies should be thread-safe or created at the right scope. Do not store the order of user A in a singleton Strategy field when the request of user B may also use it.

When policies are selected from a database, store controlled **business codes and parameters** (such as `DISCOUNT_RATE` and `0.10`); mapping codes to implementations belongs in the Strategy selection/configuration layer. Order processing may need to record the **policy version** to reproduce audited results.

## 11. Practical Exercise: Shipping Fee Strategies

You are implementing `ShippingService`. The same order has three shipping-fee algorithms:

| Strategy | Example rule | Output for 3 kg |
|---|---|---:|
| `StandardShipping` | 15.000 VND + 5.000 VND/kg | 30.000 VND |
| `ExpressShipping` | 30.000 VND + 10.000 VND/kg | 60.000 VND |
| `FreeShipping` | 0 VND | 0 VND |

Assume positive integer kilogram weights for simplicity. Then:
1. Define `ShippingStrategy` with `long feeFor(int weightKg)`.
2. Implement the three Concrete Strategies from the table. In production, define handling for fractional weights, limits, regions, and multiplication/addition overflow.
3. Implement `ShippingService` accepting `ShippingStrategy` through its constructor, validating `weightKg > 0`, and returning a nonnegative fee.
4. Select Strategy from buyer choices through a `Map` or `enum` at the composition root; do not embed `if/else` strings inside `ShippingService`.
5. Write JUnit tests for all three methods and a shared contract test; try adding `SameDayShipping` without changing the `ShippingService` core.

### Self-Check Questions

1. Must `Checkout` know the `PercentageDiscount` class? If it does, where is the dependency misplaced?
2. Does Strategy choose **the pricing algorithm** or handle **object creation**? Where can Factory participate?
3. What problems can arise if a singleton Strategy is changed through a setter under concurrent requests?
4. Why must a new Strategy preserve `0 ≤ discount ≤ subtotal` even though the Java interface only declares a `BigDecimal` return type?
5. With only two simple expressions and no changes required, why might a `switch` be preferable?

**Practical conclusion:** **Strategy = one behavioral contract + multiple algorithm implementations + a Context that delegates through composition.** Select the Strategy at configuration boundaries or per request; keep Context focused on shared business operations while enforcing input/output contracts. The pattern adds value when algorithms genuinely vary independently, not merely to eliminate every `if` statement.
