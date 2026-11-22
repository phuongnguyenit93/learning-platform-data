# Replacing Simple Strategy Classes with Lambdas When the Contract Fits

## 1. The Problem: APIs Accepting Behavior via Strategy

In the **Strategy** design pattern, the consumer of an algorithm does not decide every calculation detail itself. It accepts a **behavioral contract** (an interface), and the caller chooses the implementation. For example, a pricing service needs to vary how it calculates the total depending on the promotion:

- Standard price: keep the original total.
- VIP customer: 10% discount.
- Partner: apply a different formula.

In Java before lambdas, a simple strategy was usually written as a class implementing the interface. With Java 8+, **if the contract is a functional interface and the strategy only needs a small piece of behavior**, you can pass a lambda or a method reference instead of an implementation class. Most of the benefit comes from the API accepting **behavior directly**, not from deleting the entire Strategy structure.

Diagram example:

```text
PricingService
      │
      └── quote(subtotal, PricingStrategy strategy)
                                │
                                ├── StandardStrategy (class)
                                ├── VipStrategy      (class)
                                └── subtotal -> ...  (lambda)
```

All three approaches can provide behavior that satisfies the `PricingStrategy` contract. The `quote` method only calls the interface method; the calling code decides which strategy to use.

**Core condition:** migrating from a class to a lambda must preserve the observable behavior and the API contract. Do not replace automatically when the class still holds multiple responsibilities, lifecycle, state, configuration data, or identity that the application actually needs.

## 2. Determining Whether the Contract Fits a Lambda

A lambda in Java is assigned to a **functional interface**: an interface with exactly **one abstract method** according to the language rules. `default` methods, `static` methods, and methods corresponding to `Object`'s public methods do not turn it into an interface with multiple abstract methods.

A minimal Strategy contract:

```java
@FunctionalInterface
interface PricingStrategy {
    BigDecimal calculate(BigDecimal subtotal);
}
```

This is an interface declaration snippet; `java.math.BigDecimal` must be imported to compile in an appropriate Java file.

- Input: a `BigDecimal` holding the subtotal.
- Output: a `BigDecimal` as the result.
- One abstract behavior: `calculate`.
- Corresponding lambda: `subtotal -> subtotal.multiply(new BigDecimal("0.90"))`.

The `@FunctionalInterface` annotation is not required for lambdas to work, but it is very useful: the compiler will report an error if editing the interface makes the contract invalid. The specific method name is not what makes a lambda; it is the **signature of the single abstract method (SAM)** that determines the number and types of parameters as well as the return type.

A functional interface can have `default` methods to add utilities while still being usable with lambdas:

```java
@FunctionalInterface
interface PricingStrategy {
    BigDecimal calculate(BigDecimal subtotal);

    default String description() {
        return "pricing strategy";
    }
}
```

Conversely, if an interface declares **two independent abstract methods**, such as `calculate(...)` and `explain(...)`, it is no longer a functional interface; a lambda is not enough to provide both behaviors. You may need a concrete implementation class, a model containing two callbacks, or an API adjustment if appropriate for real needs. Do not change the design just to force lambda syntax.

## 3. Before and After: Replacing a Simple Strategy Class While Keeping the API

The following standalone runnable example shows both the traditional class-passing approach and the lambda-passing approach to **the same API**. Save it as `StrategyLambdaDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public class StrategyLambdaDemo {

    @FunctionalInterface
    interface PricingStrategy {
        BigDecimal calculate(BigDecimal subtotal);
    }

    // Old approach: a class just to implement a simple formula.
    static final class TenPercentDiscount implements PricingStrategy {
        @Override
        public BigDecimal calculate(BigDecimal subtotal) {
            return subtotal.multiply(new BigDecimal("0.90"));
        }
    }

    static final class PricingService {
        BigDecimal quote(BigDecimal subtotal, PricingStrategy strategy) {
            Objects.requireNonNull(subtotal, "subtotal");
            Objects.requireNonNull(strategy, "strategy");
            return strategy.calculate(subtotal);
        }
    }

    static BigDecimal keepOriginal(BigDecimal subtotal) {
        return subtotal;
    }

    public static void main(String[] args) {
        PricingService service = new PricingService();
        BigDecimal subtotal = new BigDecimal("100.00");

        PricingStrategy oldStrategy = new TenPercentDiscount();
        BigDecimal oldResult = service.quote(subtotal, oldStrategy);

        PricingStrategy lambdaStrategy =
                amount -> amount.multiply(new BigDecimal("0.90"));
        BigDecimal lambdaResult = service.quote(subtotal, lambdaStrategy);

        // Method reference when a matching method already exists.
        BigDecimal standardResult =
                service.quote(subtotal, StrategyLambdaDemo::keepOriginal);

        System.out.println("Class: " + oldResult);
        System.out.println("Lambda: " + lambdaResult);
        System.out.println("Method reference: " + standardResult);
    }
}
```

Compile and run on Java 17+:

```bash
javac StrategyLambdaDemo.java
java StrategyLambdaDemo
```

Output:

```text
Class: 90.0000
Lambda: 90.0000
Method reference: 100.00
```

**Arithmetic note:** `BigDecimal("100.00")` has scale 2 and `BigDecimal("0.90")` has scale 2, so `multiply` produces a result with scale 4: `90.0000`. The example intentionally keeps the scale so the console output is exact. When issuing real invoices, you need an explicit rounding/scale and currency policy; do not assume `BigDecimal` formats currency automatically.

Notable points:

1. `PricingService.quote` does not change its signature: it still takes `PricingStrategy`.
2. `TenPercentDiscount` can be replaced with `lambdaStrategy` without changing the code of `PricingService`.
3. With the same `subtotal` and formula, both approaches return the same value.
4. The lambda has the **target type** `PricingStrategy`, so the compiler infers `amount` as `BigDecimal`, and checks that the result is compatible with `BigDecimal`.
5. The method reference `StrategyLambdaDemo::keepOriginal` is another option if a method already has a matching signature.

If the old strategy class only has a simple method, with no separate state or other contract, the lambda approach usually reduces boilerplate. However, you should not delete a shared class when other places depend on its name, concrete type, or metadata; check call sites and API dependencies in a real refactoring.

## 4. Migrating Step by Step According to the Contract

When encountering a Strategy class in the codebase, you can follow this sequence:

**Step 1 — Identify the role of the class.** Does it only implement a short function, or does it also have configuration, caching, lifecycle, metrics, business name, validation, state, or dependency injection? Read the places where the interface is called and where the class is instantiated.

**Step 2 — Identify the interface used as the target type.** For example, `PricingStrategy` above has one abstract method returning `BigDecimal`. If the contract fits, a lambda can replace an implementation class.

**Step 3 — Convert the method body.** The class:

```java
final class NoDiscount implements PricingStrategy {
    @Override
    public BigDecimal calculate(BigDecimal subtotal) {
        return subtotal;
    }
}
```

can become:

```java
PricingStrategy noDiscount = subtotal -> subtotal;
```

The two snippets above are examples placed in a context where `PricingStrategy` and the `BigDecimal` import already exist; the variable declaration line goes inside a method/block, not as a standalone file.

**Step 4 — Pass the lambda where the Strategy is accepted.** For example, `service.quote(subtotal, amount -> amount)` can be used inline for a single call; if reused in multiple places, give the `PricingStrategy` variable or method a clear, meaningful name.

**Step 5 — Compare the published behavior.** Test normal inputs, boundary cases, errors, exceptions, side effects, arithmetic precision, null handling, and concurrency requirements if any. If the contract is the same but the behavior does not match, the conversion is not yet correct.

**Step 6 — Remove the old class only when nothing needs it anymore.** A public class may be an external API, a type scanned by a framework, a DI component, or directly instantiated by clients. Consider source and binary compatibility; do not delete it just because one call site can be written as a lambda.

## 5. Choosing a Built-in Functional Interface vs. a Custom Interface

Many simple strategies can be described using the built-in interfaces in `java.util.function`:

| Behavioral contract | Commonly used functional interface | SAM method |
| --- | --- | --- |
| Takes one value, returns another value | `Function<T, R>` | `R apply(T value)` |
| Takes and returns the same type | `UnaryOperator<T>` | `T apply(T value)` |
| Checks a condition | `Predicate<T>` | `boolean test(T value)` |
| Performs an action with no result | `Consumer<T>` | `void accept(T value)` |
| Creates/supplies a value without input | `Supplier<T>` | `T get()` |
| Compares the order of two values | `Comparator<T>` | `int compare(T a, T b)` |

If an API only wants to pass a `BigDecimal -> BigDecimal` transformation, it can accept `UnaryOperator<BigDecimal>`. But a custom interface like `PricingStrategy` can be valuable because it expresses the exact domain language, Javadoc, validation rules, and meaning of the contract. Do not replace a custom interface with `Function` just because it looks shorter; choosing the type is an API decision.

Example using the built-in strategy `Comparator` in Java 17; create `ComparatorStrategyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ComparatorStrategyDemo {
    record Product(String name, int price) {}

    public static void main(String[] args) {
        List<Product> items = new ArrayList<>(List.of(
                new Product("Pen", 5),
                new Product("Book", 20),
                new Product("Bag", 15)
        ));

        Comparator<Product> byPrice = Comparator.comparingInt(Product::price);
        items.sort(byPrice);

        System.out.println(
                items.stream().map(Product::name).toList());

        // Another Comparator strategy passed directly.
        items.sort((left, right) ->
                right.name().compareTo(left.name()));

        System.out.println(
                items.stream().map(Product::name).toList());
    }
}
```

Run:

```bash
javac ComparatorStrategyDemo.java
java ComparatorStrategyDemo
```

Output:

```text
[Pen, Bag, Book]
[Pen, Book, Bag]
```

Explanation: the first approach uses the `Comparator.comparingInt` factory with the method reference `Product::price`, sorting by ascending price. The second approach uses a lambda matching the `Comparator<Product>` contract to compare names in descending order: `Pen`, `Book`, `Bag`. The `List.sort` API does not need to know the concrete implementation class of the strategy.

A lambda is just an expression that provides an instance implementing the interface. Do not assume the runtime class or identity of the instance, because Java may use different implementation mechanisms.

## 6. Target Typing and Parameter Inference in API Calls

A lambda does not stand alone with a "lambda" type inferred solely from its syntax. It needs a functional interface supplied by the context: an assignment, a method argument, a cast, or an appropriate target-typing context.

Valid examples in the context of the declared `PricingService`:

```java
PricingStrategy fixed = amount -> amount;
BigDecimal result = service.quote(subtotal, amount -> amount);
```

The parameter `amount` is `BigDecimal` because `PricingStrategy.calculate(BigDecimal)` defines the contract. If you change the API parameter to `UnaryOperator<BigDecimal>`, the SAM method and target type change accordingly.

Invalid:

```java
// Missing target type for the lambda:
var strategy = amount -> amount;
```

This is an **intentionally non-compiling** example. Use `PricingStrategy strategy = amount -> amount;` or `var strategy = (PricingStrategy) (amount -> amount);` if you want to keep `var`.

Another issue is **overload ambiguity**. If an API has two overloads that both accept functional interfaces compatible with the lambda expression, the compiler may not be able to choose one. In that case, assign the lambda to a variable with an explicit type or cast it to the exact functional interface:

```java
PricingStrategy policy = amount -> amount;
service.quote(subtotal, policy);
```

There is no need to create extra classes just to "solve" type inference if only the target type is missing; however, for public APIs with many hard-to-distinguish overloads, consider designing clear method names.

## 7. Some Strategy Classes Should Not Be Replaced Directly

### 7.1. Classes Holding State and Lifecycle

Suppose a strategy has a request counter, cache, long-lived dependencies, or a connection with a lifecycle. If you replace it with a lambda that captures state, you still have to determine who owns, initializes, and closes resources, as well as thread safety when sharing the instance. A lambda does not automatically eliminate state or guarantee thread safety.

For example, a strategy provider whose configuration changes over time may make more sense as a separate object that is tested, managed by DI, and has explicit manipulation methods. If operations like `start()` / `stop()` / `calculate()` are all part of the contract, a single SAM is no longer enough to describe it.

### 7.2. Complex Strategies Needing Clear Names and Independent Testing

If the formula is long with many branches, exception handling, result explanations, or coordination of multiple dependencies, a concretely named class is usually easier to read than a 30-line inline lambda. You can still use a method reference:

```java
PricingStrategy configured = pricingEngine::calculate;
```

This is an illustrative snippet, assuming `pricingEngine.calculate(BigDecimal)` is an instance method returning `BigDecimal`. The method reference keeps the strategy wiring point concise, while the complex logic lives in a component with a name and lifecycle.

### 7.3. Contracts Based on Class Identity, Metadata, or Annotations

If the system discovers strategies via annotations on classes, configuration by class name, serialization, reflection, or dependency injection with qualifiers/types, switching to a lambda can break the discovery mechanism. Java does not guarantee the generated class name for a lambda and does not turn a lambda instance into a component with metadata like an annotated class. Keep the class or change the registry/metadata architecture before migrating.

### 7.4. Contracts Controlling Checked Exceptions

The SAM determines which checked exceptions a lambda is allowed to throw. For instance, `Function<T,R>.apply` does not declare `throws IOException`; a lambda that directly calls a method capable of throwing a checked `IOException` must handle or translate the error appropriately. If the strategy genuinely has a checked exception contract, a custom functional interface such as:

```java
@FunctionalInterface
interface FileStrategy {
    String load(String path) throws java.io.IOException;
}
```

can still use a lambda while preserving the error contract. Choosing a type just because `Function` is built-in and losing the exception semantics is wrong.

### 7.5. Needing Multiple Coordinated Behaviors

A strategy consisting of independent `validate`, `execute`, and `rollback` methods cannot be fully represented by a single lambda attached to an interface with three abstract methods. Do not automatically split them into three separate callbacks if they need to share invariants, resources, and lifecycle. Using an object with the full interface makes it easier to uphold the contract.

## 8. Capturing and Managing Dependencies When Using Lambdas

A lambda can reference local variables from the enclosing scope if those variables are `final` or **effectively final**. When a lambda captures a mutable object, it holds a reference to that object; there is no guarantee that the inner object is immutable or thread-safe.

Example of a method that creates a strategy based on a discount rate:

```java
static PricingStrategy discount(BigDecimal rate) {
    Objects.requireNonNull(rate);
    return subtotal -> subtotal.multiply(BigDecimal.ONE.subtract(rate));
}
```

This is a static method snippet placed in a class with `PricingStrategy`, with `BigDecimal` and `Objects` imported. The parameter variable `rate` is effectively final. You need to separately validate the valid range of `rate` (for example, from 0 to 1) and business rounding rules; the compiler does not check those constraints automatically.

A common mistake:

```java
int percent = 10;
PricingStrategy p = subtotal ->
        subtotal.multiply(
                BigDecimal.valueOf(100 - percent)
                        .movePointLeft(2));
percent = 20; // Invalid: the captured variable percent is not effectively final.
```

This is an **intentionally non-compiling counterexample**. If you want a strategy with a fixed rate, create a `final int percent = 10;` variable and use it. If you want a rate that can be updated, model it as state/configuration with clear ownership rather than trying to mutate a captured local variable.

In particular, a lambda should not be used as a business identity, cache key, or logging name. Attach a separate ID such as `"STANDARD"`, `"VIP_10"` to allow controlled lookup.

## 9. Registering Strategies by Business Name, Passing Lambdas to the API

When there are many small strategies, you can store them in a `Map<String, PricingStrategy>` or a registry, combining a **stable ID** with behavior. Create `PricingRegistryDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;
import java.util.function.UnaryOperator;

public class PricingRegistryDemo {
    static BigDecimal quote(
            BigDecimal subtotal,
            UnaryOperator<BigDecimal> policy) {
        return Objects.requireNonNull(policy).apply(
                Objects.requireNonNull(subtotal));
    }

    public static void main(String[] args) {
        Map<String, UnaryOperator<BigDecimal>> policies = Map.of(
                "STANDARD", amount -> amount,
                "VIP_10", amount ->
                        amount.multiply(new BigDecimal("0.90"))
        );

        BigDecimal subtotal = new BigDecimal("50.00");
        System.out.println(
                quote(subtotal, policies.get("STANDARD")));
        System.out.println(
                quote(subtotal, policies.get("VIP_10")));
    }
}
```

Run:

```bash
javac PricingRegistryDemo.java
java PricingRegistryDemo
```

Output:

```text
50.00
45.0000
```

The application knows strategies by the published string key, not by the lambda's `getClass().getName()`. In production systems, you can use an `enum` or value object for the key to reduce mistakes; you must handle the case where a key does not exist, because `Map.get` will return `null` and the `quote` method in the example will throw an error.

Regarding execution timing, `Map.of` stores the strategy instances when the map is initialized; the lambda code inside is only invoked when `quote` calls `apply`. Do not assume every lambda is always created as a new instance by the JVM or always uses a singleton; identity is not a mechanism for identifying strategies.

## 10. Before/After Testing to Protect the Contract

When migrating a Strategy class to a lambda, the main question is: **can API users observe any unintended changes?** Basic cases should be tested with the same set of inputs:

| Scenario | What to compare |
| --- | --- |
| Normal input | Are the return values of the class and the lambda equivalent under the contract? |
| Boundary data | Are 0, negative numbers, empty strings, and large values handled properly? |
| Invalid input | Are validation and exception types/messages preserved as required? |
| Decimal results | Are scale, rounding, currency rules, and precision compatible? |
| Side effects | Have ordering, invocation counts, transactions, or required logging changed? |
| Repeated reuse | Are there unintended changes in state and concurrency safety? |
| External code using the class | Does it depend on a public constructor, annotations, serialization, DI, or reflection? |

In simple examples, you can test by comparing results directly:

```java
BigDecimal subtotal = new BigDecimal("100.00");
PricingStrategy classBased = new TenPercentDiscount();
PricingStrategy lambdaBased =
        n -> n.multiply(new BigDecimal("0.90"));

boolean sameValue =
        classBased.calculate(subtotal)
                .compareTo(lambdaBased.calculate(subtotal)) == 0;
```

The snippet above assumes the types from `StrategyLambdaDemo.java` and is placed inside a method. For the value `100.00`, `sameValue` is `true`. Choose `compareTo` when you only need to compare the **numeric value** of a `BigDecimal`; `equals` also distinguishes scale. If scale is part of the API contract, also check the exact scale or compare with `equals` as required.

Checks like `oldStrategy == lambdaStrategy`, `oldStrategy.getClass()`, or whether evaluating a lambda twice returns the same instance **do not prove the business contract is correct**. Prioritize testing the specified results and side effects.

## 11. Common Mistakes

1. **Replacing a class with multiple responsibilities with a large inline lambda.** Extract the logic into a named method, a method reference, or keep the class when state, lifecycle, and complex contracts are needed.
2. **Not verifying the SAM.** Two abstract methods make the interface no longer a functional interface; check the signature and use `@FunctionalInterface` when appropriate.
3. **Losing checked exception semantics.** Changing an interface declaring `throws` to `Function` can prevent compilation or force changes in error handling. Keep the necessary exception contract.
4. **Changing a public API type without checking call sites.** Even if the SAM looks similar in shape, changing from `PricingStrategy` to `Function<BigDecimal,BigDecimal>` can still affect callers, generic inference, and binary compatibility.
5. **Capturing mutable state without managing thread safety.** A lambda can hold the same mutable object shared by multiple threads; it does not copy or synchronize state automatically.
6. **Relying on a lambda's class name/identity for lookup.** Use a business ID, enum, or explicit registry.
7. **Forgetting monetary calculation rules.** Migrating to a lambda does not eliminate requirements for `BigDecimal`, rounding, scale, precision, and invalid input handling.
8. **Testing only a single "happy path" case.** Test boundary data, errors, side effects, and contract behaviors that must be preserved.
9. **Overusing built-in generic interfaces.** If the domain needs a clear, meaningful contract and Javadoc, a custom functional interface is usually easier to maintain.
10. **Assuming "lambda = async".** A lambda only represents behavior; passing it to an API does not make it run in parallel or asynchronously. When and where it runs is decided by the API receiving the callback.

## 12. Quick Check Exercise

Suppose you have the contract:

```java
@FunctionalInterface
interface FeePolicy {
    long charge(long amount);
}
```

And the class:

```java
final class FlatFee implements FeePolicy {
    @Override
    public long charge(long amount) {
        return amount + 5L;
    }
}
```

Do the following:

1. Replace creating `new FlatFee()` at a call site with a lambda having the same behavior.
2. If a `static long addFee(long amount)` method already exists, write the corresponding method reference.
3. Explain why `FeePolicy` can still have `default String name()` without affecting lambda usage.
4. Identify when you should keep the `FlatFee` class instead of deleting it.

Reference answer: `FeePolicy policy = amount -> amount + 5L;`; the method reference is `FeePolicy policy = MyClass::addFee;` if `addFee` is a matching static method of `MyClass`. A default method with a body is not a second abstract SAM. You should keep the class if it is a public API in use, has annotations/metadata, manages state, or provides a clear domain name that is widely used.

## 13. Concluding Principles for Designing Behavior-Accepting APIs

Only migrate from a Strategy class to a lambda when all three conditions are met:

1. **Valid interface:** there is a single abstract method that actually needs to be implemented, with a clear contract signature, exceptions, and semantics.
2. **Sufficiently simple strategy:** the implementation is primarily a small behavior; there is no need to keep a class to own multiple responsibilities, lifecycle, metadata, or identity.
3. **Behavior is preserved:** outputs, errors, side effects, concurrency safety, and external dependencies still adhere to the contract.

Keep the API's interface so that the consumer does not need to know whether a class or a lambda is executing. When you want to express multiple strategies, pass them as function values with a clear target type; when you need to manage or identify them, use business names/IDs independent of the implementation. In this way, Strategy and functional programming complement each other: **Strategy defines the point where behavior can vary, and lambdas provide a concise implementation when the contract fits**.

**References:** Java Language Specification §9.8 (Functional Interfaces) and §15.27 (Lambda Expressions); Java SE API `java.util.function`, `java.util.Comparator`, `java.math.BigDecimal`.