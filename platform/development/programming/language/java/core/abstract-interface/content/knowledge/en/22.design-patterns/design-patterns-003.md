# Strategy: Swapping Algorithms via an Interface in Java

**Strategy** is a behavioral design pattern that allows defining a family of algorithms, encapsulating each algorithm into a separate implementation, and swapping them without rewriting the object that uses the algorithm. In Java, an interface is typically the common point for strategies to follow the same contract.

For example, a checkout screen may calculate prices using multiple discount policies. If each policy is written as a class implementing the same interface, the program can select the appropriate policy at runtime. The checkout class does not need to know the details of how each policy performs its calculation.

## 1. The Problem That Strategy Solves

Suppose an application has three ways to apply a discount: no discount, a percentage discount, and a fixed amount discount. If all of them are grouped into one large method with many **if/else** branches, every time a new policy is added, we have to modify that method. As the number of policies grows, the coordinating class knows too many details and becomes hard to test.

An initial implementation might look like this:

~~~java
BigDecimal totalFor(
        BigDecimal subtotal,
        String discountType) {
    if (discountType.equals("NONE")) {
        return subtotal;
    } else if (discountType.equals("PERCENT")) {
        return subtotal.multiply(new BigDecimal("0.90"));
    } else if (discountType.equals("FIXED")) {
        return subtotal.subtract(new BigDecimal("15.00"));
    }
    throw new IllegalArgumentException("Unknown discount type");
}
~~~

This is only a snippet illustrating the problem: the logic of multiple algorithms is concentrated in one place, identifier strings can be mistyped, and adding an algorithm requires modifying the coordinating code. This snippet also does not yet fully handle currency rules, such as limiting the total amount to be non-negative.

Strategy separates each algorithm into a separate implementation. The class that uses it holds a reference to the interface and calls the interface method to execute the selected behavior.

## 2. Structure of Strategy

A Strategy design typically has three roles:

1. **Strategy interface**: declares the common contract, for example **DiscountStrategy**.
2. **Concrete strategies**: classes such as **NoDiscount**, **PercentageDiscount**, and **FixedDiscount**, each implementing one algorithm.
3. **Context**: the object that uses the algorithm. In this example, **Checkout** calls the interface it is provided and can receive a different strategy at runtime.

Call flow:

~~~mermaid
classDiagram
    class DiscountStrategy {
        <<interface>>
        +discountFor(subtotal) BigDecimal
        +name() String
    }
    class NoDiscount
    class PercentageDiscount
    class FixedDiscount
    class Checkout {
        -strategy DiscountStrategy
        +setStrategy(strategy)
        +totalFor(subtotal) BigDecimal
    }
    DiscountStrategy <|.. NoDiscount
    DiscountStrategy <|.. PercentageDiscount
    DiscountStrategy <|.. FixedDiscount
    Checkout --> DiscountStrategy : delegates to
~~~

The key arrow in the design is that **Checkout** depends on **DiscountStrategy**, not directly on a specific discount class. The concrete strategies all satisfy the same contract, so they can be passed into **Checkout** interchangeably.

## 3. Complete Example with Java 17+

The example uses **BigDecimal** for monetary calculations instead of **double**, because ordinary decimal numbers cannot always be represented accurately in binary floating-point. Each strategy only decides the discount amount; **Checkout** applies bounds so that the discount is non-negative and does not exceed the original price.

Save all of the following code to the file **StrategyDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

interface DiscountStrategy {
    BigDecimal discountFor(BigDecimal subtotal);

    String name();
}

final class NoDiscount implements DiscountStrategy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return BigDecimal.ZERO;
    }

    @Override
    public String name() {
        return "No discount";
    }
}

final class PercentageDiscount implements DiscountStrategy {
    private final BigDecimal rate;

    PercentageDiscount(BigDecimal rate) {
        Objects.requireNonNull(rate, "rate");
        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "rate must be between 0 and 1");
        }
        this.rate = rate;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(rate)
                .setScale(2, RoundingMode.HALF_UP);
    }

    @Override
    public String name() {
        return rate.multiply(new BigDecimal("100"))
                .stripTrailingZeros().toPlainString() + "% off";
    }
}

final class FixedDiscount implements DiscountStrategy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.compareTo(BigDecimal.ZERO) < 0) {
            throw new IllegalArgumentException(
                    "amount must not be negative");
        }
        this.amount = amount.setScale(2, RoundingMode.HALF_UP);
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return amount;
    }

    @Override
    public String name() {
        return amount.toPlainString() + " off";
    }
}

final class Checkout {
    private DiscountStrategy strategy;

    Checkout(DiscountStrategy strategy) {
        setStrategy(strategy);
    }

    void setStrategy(DiscountStrategy strategy) {
        this.strategy = Objects.requireNonNull(
                strategy, "strategy");
    }

    BigDecimal totalFor(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.compareTo(BigDecimal.ZERO) < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }

        BigDecimal discount = strategy.discountFor(subtotal);
        discount = discount.max(BigDecimal.ZERO).min(subtotal);
        return subtotal.subtract(discount)
                .setScale(2, RoundingMode.HALF_UP);
    }

    String strategyName() {
        return strategy.name();
    }
}

public class StrategyDemo {
    public static void main(String[] args) {
        BigDecimal subtotal = new BigDecimal("100.00");
        Checkout checkout = new Checkout(new NoDiscount());

        System.out.println(checkout.strategyName() + ": "
                + checkout.totalFor(subtotal).toPlainString());

        checkout.setStrategy(
                new PercentageDiscount(new BigDecimal("0.10")));
        System.out.println(checkout.strategyName() + ": "
                + checkout.totalFor(subtotal).toPlainString());

        checkout.setStrategy(
                new FixedDiscount(new BigDecimal("15.00")));
        System.out.println(checkout.strategyName() + ": "
                + checkout.totalFor(subtotal).toPlainString());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac StrategyDemo.java
java StrategyDemo
~~~

Stdout output:

~~~text
No discount: 100.00
10% off: 90.00
15.00 off: 85.00
~~~

### Reading the Example Step by Step

- **DiscountStrategy** defines two operations that every strategy must provide: calculating the discount amount and returning the strategy name.
- **NoDiscount**, **PercentageDiscount**, and **FixedDiscount** implement different algorithms while sharing the same interface type.
- **Checkout** is the context. It calls **strategy.discountFor(...)** without needing to check which class the current strategy belongs to.
- **setStrategy(...)** allows swapping the algorithm at runtime. After swapping, the same call to **totalFor(...)** uses the behavior of the new strategy.
- **Objects.requireNonNull** blocks passing null references; the strategy constructors validate parameters that could make the algorithm meaningless.
- **Checkout** ensures the discount stays within the range from 0 to the original price. This rule keeps the total amount non-negative even if a strategy added later contains a bug.

Substitution only requires conforming to the interface. There is no need to modify the code of **Checkout** when adding a new strategy such as a member discount or a seasonal promotion.

## 4. Interface, Inheritance, and Composition

Strategy typically combines an **interface with composition**. The context holds a strategy object and delegates part of the work to it:

~~~java
private DiscountStrategy strategy;
~~~

This relationship is different from inheritance. **Checkout** does not need to **extends PercentageDiscount**; it can use any object that implements **DiscountStrategy**. As a result, algorithm selection is not tightly coupled to the context's inheritance hierarchy.

The interface makes the common contract explicit. Each strategy can still have its own fields and constructor to hold required parameters, such as **rate** or **amount**. The context relies only on the public methods of the interface.

## 5. How to Select a Strategy?

In real-world applications, selecting a strategy is typically based on configuration, request type, business state, or user data. For example, a service layer may decide the discount policy and then pass the strategy object into **Checkout**.

External data should not be allowed to directly create arbitrary class names via reflection. Instead, map validated configuration values to permitted strategies:

~~~java
DiscountStrategy strategy = switch (campaignType) {
    case "NONE" -> new NoDiscount();
    case "TEN_PERCENT" ->
            new PercentageDiscount(new BigDecimal("0.10"));
    case "FIXED_15" ->
            new FixedDiscount(new BigDecimal("15.00"));
    default -> throw new IllegalArgumentException(
            "Unsupported campaign: " + campaignType);
};
~~~

This is a snippet to illustrate selection, not a standalone program. It assumes the **campaignType** variable has already been declared and validated according to the application's data model. Strategy selection can use **switch**, a factory, or dependency injection; the core point of Strategy is that the part using the algorithm works through an interface.

## 6. When Should You Use Strategy?

Strategy is appropriate when:

- There are multiple interchangeable algorithms or policies.
- You want to select behavior at runtime instead of fixing behavior inside a large conditional chain.
- You want to test each algorithm independently and test the context using a fake strategy.
- You want to add new variants while reducing the number of changes in the class using the algorithm.
- The algorithms share the same purpose but differ in how they are implemented, such as shipping fee calculation, authentication, routing, data compression, or pricing policy selection.

Strategy can be overkill when there is only one stable algorithm and no need for extension. Adding an interface and multiple classes just to wrap a simple calculation can make the program harder to read. Create separate strategies when they represent genuine choices in the business domain or when such variation is likely to arise.

## 7. Benefits and Trade-offs

**Benefits**

- Reduces coupling between the context and concrete algorithms.
- Adds an algorithm by creating a new class that implements the interface.
- Makes testing algorithms individually easier.
- Prevents a context class from bloating with many conditional branches for interchangeable behaviors.

**Trade-offs**

- Increases the number of types and objects in the program.
- Requires a place that decides which strategy is used; the interface does not choose the strategy by itself.
- If there are too many minor variants, finding the class currently executing a behavior can take time.
- Swapping a strategy at runtime must be managed carefully if the context is shared across multiple threads. This example assumes each **Checkout** is used sequentially; if a single instance is shared across multiple threads, updating and reading the strategy must be designed to be safe.

## 8. Common Mistakes

- **Putting if/else branches inside the context and calling it Strategy.** If all algorithms still live in one coordinating method, the varying part has not been extracted.
- **Making the context depend directly on implementation classes.** Instantiate the strategy in a composition root, factory, or configuration layer, and then pass it into the context through the interface.
- **Putting too many responsibilities into the interface.** Only declare the common operations that the context actually needs; specific details can reside inside each strategy.
- **Skipping parameter validation.** A percentage discount strategy needs to define a valid value range; monetary algorithms need to agree on rounding behavior.
- **Confusing Strategy with merely changing data.** Configuration parameters can change the result of the same algorithm. Strategy is especially useful when there are distinct implementations that need to be swapped through the same contract.
- **Forgetting where the strategy is selected.** This pattern separates the point of use from the algorithm; it does not eliminate the need to decide which algorithm suits each request.

## 9. How to Remember It

Strategy turns interchangeable algorithms into objects that conform to the same interface. The context holds a reference to the interface and delegates work to it, so the algorithm can be swapped without rewriting the context.

When applying it, identify which part changes frequently, define a minimal contract for that part, write each algorithm as a separate implementation, and let an appropriate layer decide which strategy is used. Only use this pattern when the benefits of decoupling and swapping algorithms outweigh the cost of additional types.
