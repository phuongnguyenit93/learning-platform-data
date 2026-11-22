# Polymorphism and Multiple Implementations of the Same Operation in Java

In object-oriented programming (OOP), **polymorphism** allows the same code to issue **the same method call** to different objects while each object performs the operation in a way appropriate to its type.

For example, an e-commerce system must calculate shipping fees. For the same parcel, standard, express, and economy delivery may have different pricing formulas and estimated delivery times. Instead of having the checkout screen test `if (loaiGiaoHang == ...)` and calculate each formula, we define a `ShippingPolicy.quote(parcel)` contract and let **each implementation take responsibility** for its own calculation.

Key points:

- **Shared operation**: `quote(Parcel)` — requests a shipping quote.
- **Different implementations**: `StandardShipping`, `ExpressShipping`, `EconomyShipping`.
- **Shared consuming code**: depends only on `ShippingPolicy` without knowing the pricing formulas.
- **At runtime**: Java invokes the implementation appropriate to the **actual type of the object** referenced.

## 1. One Operation, Multiple Behaviors

The contract can be expressed as an interface:

~~~java
interface ShippingPolicy {
    ShippingQuote quote(Parcel parcel);
}
~~~

Three shipping types implement the same method:

~~~java
class StandardShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        // Tính phí tiêu chuẩn.
        // ...
        return null; // Chỉ là đoạn khung minh họa, không phải code hoàn chỉnh.
    }
}

class ExpressShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        // Tính phí hỏa tốc.
        // ...
        return null; // Đoạn khung.
    }
}
~~~

The shared consuming code:

~~~java
ShippingPolicy policy = /* một đối tượng triển khai ShippingPolicy */;
ShippingQuote result = policy.quote(parcel);
~~~

The call **does not change** when `policy` refers to an `StandardShipping` instead of an `ExpressShipping`. The difference lies in **which method implementation** runs.

Polymorphism based on overridden or implemented instance methods is commonly called **dynamic polymorphism** (*runtime polymorphism*). Java does not select behavior by looking at the variable name `policy`; it uses the **actual referenced object**.

## 2. Complete Java Example: Multiple Shipping-Fee Strategies

Suppose the system supports three service plans:

| Plan | Inner-city base fee | Outer-city base fee | Weight surcharge | Estimated delivery time |
| --- | ---: | ---: | --- | --- |
| Economy | 18.000 VND | 28.000 VND | 2.000 VND for each started kilogram **after the first kilogram** | 4–6 days |
| Standard | 20.000 VND | 35.000 VND | 5.000 VND for each started kilogram **after the first kilogram** | 2–4 days |
| Express | 50.000 VND | 70.000 VND | 15.000 VND per started 500 g, **including the first 500 g** | 1 day |

These are **hypothetical figures** for practicing Java, not an actual carrier's rates. Each policy supports both zones so implementations remain substitutable under the shared contract.

Save the following code as **`ShippingPolymorphismDemo.java`**. It runs standalone with **Java 11+** and requires only a JDK.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class ShippingPolymorphismDemo {

    enum Zone {
        INNER_CITY, OUTER_CITY
    }

    // Dữ liệu kiện hàng: không sửa được sau khi tạo.
    static final class Parcel {
        private final String trackingCode;
        private final int weightGrams;
        private final Zone zone;

        Parcel(String trackingCode, int weightGrams, Zone zone) {
            String code = Objects.requireNonNull(
                    trackingCode, "trackingCode").trim();
            if (code.isEmpty()) {
                throw new IllegalArgumentException("Mã kiện hàng bị rỗng");
            }
            if (weightGrams <= 0) {
                throw new IllegalArgumentException(
                        "Khối lượng phải lớn hơn 0");
            }
            this.trackingCode = code;
            this.weightGrams = weightGrams;
            this.zone = Objects.requireNonNull(zone, "zone");
        }

        int getWeightGrams() {
            return weightGrams;
        }

        Zone getZone() {
            return zone;
        }
    }

    // Kết quả dùng chung, bất kể cách tính phí.
    static final class ShippingQuote {
        private final String serviceName;
        private final BigDecimal feeVnd;
        private final int estimatedDays;

        ShippingQuote(String serviceName, BigDecimal feeVnd,
                      int estimatedDays) {
            this.serviceName = Objects.requireNonNull(
                    serviceName, "serviceName");
            this.feeVnd = Objects.requireNonNull(feeVnd, "feeVnd");
            if (feeVnd.signum() < 0 || estimatedDays <= 0) {
                throw new IllegalArgumentException(
                        "Báo giá hoặc thời gian không hợp lệ");
            }
            this.estimatedDays = estimatedDays;
        }

        String getServiceName() {
            return serviceName;
        }

        BigDecimal getFeeVnd() {
            return feeVnd;
        }

        int getEstimatedDays() {
            return estimatedDays;
        }
    }

    // Hợp đồng chung cho MỌI chính sách giao hàng.
    interface ShippingPolicy {
        ShippingQuote quote(Parcel parcel);
    }

    static final class EconomyShipping implements ShippingPolicy {
        @Override
        public ShippingQuote quote(Parcel parcel) {
            Objects.requireNonNull(parcel, "parcel");

            long extraKg = (parcel.getWeightGrams() - 1L) / 1000L;
            long base = parcel.getZone() == Zone.INNER_CITY
                    ? 18_000L : 28_000L;
            long fee = base + extraKg * 2_000L;
            int days = parcel.getZone() == Zone.INNER_CITY ? 4 : 6;

            return new ShippingQuote(
                    "Tiết kiệm", BigDecimal.valueOf(fee), days);
        }
    }

    static final class StandardShipping implements ShippingPolicy {
        @Override
        public ShippingQuote quote(Parcel parcel) {
            Objects.requireNonNull(parcel, "parcel");

            long extraKg = (parcel.getWeightGrams() - 1L) / 1000L;
            long base = parcel.getZone() == Zone.INNER_CITY
                    ? 20_000L : 35_000L;
            long fee = base + extraKg * 5_000L;
            int days = parcel.getZone() == Zone.INNER_CITY ? 2 : 4;

            return new ShippingQuote(
                    "Tiêu chuẩn", BigDecimal.valueOf(fee), days);
        }
    }

    static final class ExpressShipping implements ShippingPolicy {
        @Override
        public ShippingQuote quote(Parcel parcel) {
            Objects.requireNonNull(parcel, "parcel");

            long unitsOf500g =
                    (parcel.getWeightGrams() + 499L) / 500L;
            long base = parcel.getZone() == Zone.INNER_CITY
                    ? 50_000L : 70_000L;
            long fee = base + unitsOf500g * 15_000L;

            return new ShippingQuote(
                    "Hỏa tốc", BigDecimal.valueOf(fee), 1);
        }
    }

    // Mã sử dụng chỉ phụ thuộc vào hợp đồng ShippingPolicy.
    static final class CheckoutService {
        private final ShippingPolicy policy;

        CheckoutService(ShippingPolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        ShippingQuote estimate(Parcel parcel) {
            return policy.quote(parcel);
        }
    }

    public static void main(String[] args) {
        Parcel parcel = new Parcel(
                "PK-001", 1500, Zone.INNER_CITY);

        List<ShippingPolicy> policies = List.of(
                new EconomyShipping(),
                new StandardShipping(),
                new ExpressShipping());

        for (ShippingPolicy policy : policies) {
            CheckoutService checkout = new CheckoutService(policy);
            ShippingQuote quote = checkout.estimate(parcel);

            System.out.println(
                    quote.getServiceName() + ": "
                    + quote.getFeeVnd().toPlainString() + " VND"
                    + ", dự kiến " + quote.getEstimatedDays() + " ngày");
        }
    }
}
~~~

Run:

~~~bash
javac ShippingPolymorphismDemo.java
java ShippingPolymorphismDemo
~~~

Output:

~~~text
Tiết kiệm: 20000 VND, dự kiến 4 ngày
Tiêu chuẩn: 25000 VND, dự kiến 2 ngày
Hỏa tốc: 95000 VND, dự kiến 1 ngày
~~~

### Checking the Calculations

The parcel weighs **1.500 g** and is in the **inner-city** zone:

- **Economy**: 18.000 + 1 × 2.000 = **20.000 VND**, because 1 additional kilogram begins after the first.
- **Standard**: 20.000 + 1 × 5.000 = **25.000 VND**.
- **Express**: 50.000 + 3 × 15.000 = **95.000 VND**, because 1.500 g comprises three 500 g units.

All methods return `ShippingQuote`, so checkout code can receive and display a quote **without changing the data structure** for each plan.

### Why Is This Polymorphism Rather Than Just Three Different Functions?

The commonality is not merely that all three classes have a method named `quote`. All three **`implements ShippingPolicy`**, establishing a clear shared type contract.

Inside the loop:

~~~java
for (ShippingPolicy policy : policies) {
    ShippingQuote quote = policy.quote(parcel);
}
~~~

On each iteration:

| Iteration | Declared type of `policy` | Actual object | `quote` implementation invoked |
| --- | --- | --- | --- |
| 1 | `ShippingPolicy` | `EconomyShipping` | `EconomyShipping.quote` |
| 2 | `ShippingPolicy` | `StandardShipping` | `StandardShipping.quote` |
| 3 | `ShippingPolicy` | `ExpressShipping` | `ExpressShipping.quote` |

**One call in the consuming code, multiple behaviors in the implementations**: this is a typical example of dynamic polymorphism.

## 3. Type Relationships and How Java Selects Behavior

~~~mermaid
classDiagram
    class ShippingPolicy {
        <<interface>>
        +quote(Parcel) ShippingQuote
    }
    class EconomyShipping {
        +quote(Parcel) ShippingQuote
    }
    class StandardShipping {
        +quote(Parcel) ShippingQuote
    }
    class ExpressShipping {
        +quote(Parcel) ShippingQuote
    }
    class CheckoutService {
        -policy ShippingPolicy
        +estimate(Parcel) ShippingQuote
    }
    ShippingPolicy <|.. EconomyShipping
    ShippingPolicy <|.. StandardShipping
    ShippingPolicy <|.. ExpressShipping
    CheckoutService --> ShippingPolicy : depends on
~~~

The dashed triangle arrows represent **implements** relationships. `CheckoutService` holds a reference of type `ShippingPolicy`; it does not need three separate fields for the three plans.

When one quote is calculated:

~~~mermaid
sequenceDiagram
    actor App as Main
    participant Checkout as CheckoutService
    participant Policy as ShippingPolicy
    participant Express as ExpressShipping

    App->>Checkout: estimate(parcel)
    Checkout->>Policy: quote(parcel)
    Note over Policy,Express: Tham chiếu có kiểu ShippingPolicy<br/>nhưng object thực là ExpressShipping
    Policy->>Express: Dispatch tới ExpressShipping.quote()
    Express-->>Policy: ShippingQuote(95000, 1)
    Policy-->>Checkout: ShippingQuote
    Checkout-->>App: ShippingQuote
~~~

The diagram uses `ShippingPolicy` as a **contract role**; it does not imply that Java creates an instance of the interface. In an actual execution, the call is performed on the `ExpressShipping` instance referenced by `CheckoutService.policy`.

### Distinguishing Static Types from Runtime Types

~~~java
ShippingPolicy policy = new ExpressShipping();
~~~

- The variable `policy` has the **static type** `ShippingPolicy`: the compiler allows calls to methods declared in the interface, such as `quote`.
- The object's **actual type** is `ExpressShipping`: calling `policy.quote(...)` invokes the `ExpressShipping` implementation.

If a concrete class has a method not declared by the interface:

~~~java
class DebugShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        return new ShippingQuote("Debug", BigDecimal.ZERO, 1);
    }

    public void resetDebugCounters() {
        System.out.println("Đã reset");
    }
}
~~~

~~~java
ShippingPolicy policy = new DebugShipping();
policy.quote(parcel); // Hợp lệ.

// policy.resetDebugCounters(); // Lỗi biên dịch: interface không khai báo.
~~~

The compiler uses the **reference type** to determine which operations are callable; once an implemented or overridden instance method is invoked, the **runtime type** determines how it executes.

## 4. Replace "What Type Is This?" with "Perform the Operation"

If checkout repeatedly checks `"ECONOMY"`, `"STANDARD"`, and `"EXPRESS"` and duplicates their formulas, adding a new policy requires changes in many places. Instead, consuming code simply requests:

~~~java
ShippingQuote quote = policy.quote(parcel);
~~~

The location that selects a delivery plan **may still use** `switch`, `Map<String,ShippingPolicy>`, or configuration:

~~~java
Map<String, ShippingPolicy> options = Map.of(
    "economy", new EconomyShipping(),
    "express", new ExpressShipping()
);
ShippingPolicy selected = options.get("express");
if (selected == null) throw new IllegalArgumentException("Gói không hợp lệ");
ShippingQuote quote = selected.quote(parcel);
~~~

This illustration requires `import java.util.Map;` and must be placed in an appropriate Java method. **Selecting a strategy at the boundary** does not mean duplicating its pricing formula in every service. The lesson *Using Polymorphism Instead of Type-Based Conditionals* covers step-by-step refactoring, regression tests, and cases where `if/switch` remains appropriate.

## 5. `@Override` Confirms the Link Between Contract and Implementation

Each concrete `ShippingPolicy` must provide `public ShippingQuote quote(Parcel)`. The `@Override` annotation lets the compiler catch misspellings or incorrect parameter lists:

~~~java
class ExampleShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        return new ShippingQuote("Mẫu", BigDecimal.ZERO, 1);
    }
}
~~~

This example places `ExampleShipping` **inside** `ShippingPolymorphismDemo` so it can directly use nested types from the main program (and `BigDecimal` is already imported). If moved to a top-level class, nested type names must be qualified correctly. Changing `quote(Parcel)` to `quote(String)` no longer implements the required signature. The compiler checks compatible types, access, return types, and checked exceptions; it **cannot prove** nonnegative fees, valid delivery times, side effects, or correct business results. The lesson *Method Overriding and Runtime Method Selection* examines overriding rules, `final`, and `super` calls in greater depth.

## 6. Overriding Is Not Overloading

~~~java
class Animal {
    String sound() { return "Âm thanh"; }
}
class Dog extends Animal {
    @Override String sound() { return "Gâu"; }
}
Animal a = new Dog();
System.out.println(a.sound()); // Gâu
~~~

This is an **override**: the same `sound()` signature is implemented according to the runtime `Dog` object. By contrast, `print(Object)` and `print(String)` are **overloads**, meaning signatures with different parameters; the compiler selects one based on the static types at the call site. Thus `Object text = "Java"; print(text)` selects the `Object` overload when both exist, even though the actual object is a `String`.

A Java call may involve **two stages**: selecting an overload at compile time and then dispatching to an override of the selected signature at runtime. The lesson *Static Method Resolution and Dynamic Dispatch* explains these two stages; *Distinguishing Overriding from Overloading* offers concrete tests.

## 7. A Shared Contract May Be an Interface or Parent Class

`ShippingPolicy` represents a capability, so an `interface` is appropriate for the primary example. If several shipping types genuinely share constructors, state, and part of the pricing algorithm, an abstract class that `implements ShippingPolicy` can share the common calculation. Concrete subclasses may then override only a designated hook.

Do not introduce an abstract superclass just because two methods coincidentally share a few lines: inheritance creates obligations between parents and children. For independently replaceable strategies, an interface plus composition is often easier to maintain. Either way, classes must preserve the same `quote(Parcel)` contract.

## 8. Selecting Implementations at the Application Composition Boundary

~~~java
CheckoutService standard =
    new CheckoutService(new StandardShipping());
CheckoutService express =
    new CheckoutService(new ExpressShipping());
~~~

Two different `CheckoutService` objects depend on the same `ShippingPolicy` type. Every `estimate(parcel)` call forwards to the supplied policy's `quote` method, so checkout needs to know neither the formula nor the concrete class.

This is simple constructor injection using plain Java. It supports substitution and testing when the contract is genuinely clear; adding a policy may still require registration at the selection point, UI updates, and tests for the new formula.

## 9. Misconceptions to Recognize Before Going Deeper

| Claim | What Is True in Java |
|---|---|
| Two classes with the same `quote(Parcel)` automatically work as `ShippingPolicy` | A valid `implements`/`extends` relationship or adapter is required; Java uses nominal typing |
| Adding an overload `quote(String)` in a subclass changes `quote(Parcel)` behavior | No; an override requires the matching signature |
| Same-named static methods or public fields are dynamically polymorphic | No; static methods and fields follow hiding and compile-time lookup rules |
| `instanceof` checks are required everywhere to select a concrete class | If `ShippingPolicy.quote` exists, call that method directly |
| All implementations compile, so substitution is guaranteed safe | They must also preserve the contract's preconditions, results, errors, and side effects |

The lessons *Distinguishing Member Hiding from Overriding* and *Scope of Polymorphism for Methods and Fields* separately illustrate fields, static methods, private methods, and getters. For now, remember the basic rule: **dynamic polymorphism applies when a contract's instance method is invoked and an appropriate implementation is selected from the runtime object**.

## 10. Testing One Contract Across Multiple Implementations

When several classes implement `ShippingPolicy`, test their **shared contract** in addition to each pricing formula. The following example uses **JUnit 5**, which requires a JUnit Jupiter dependency and suitable test runner.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class ShippingPolicyContractTest {

    @Test
    void everyPolicyReturnsAValidQuote() {
        ShippingPolymorphismDemo.Parcel parcel =
                new ShippingPolymorphismDemo.Parcel(
                        "PK-TEST", 1500,
                        ShippingPolymorphismDemo.Zone.INNER_CITY);

        List<ShippingPolymorphismDemo.ShippingPolicy> policies =
                List.of(
                        new ShippingPolymorphismDemo.EconomyShipping(),
                        new ShippingPolymorphismDemo.StandardShipping(),
                        new ShippingPolymorphismDemo.ExpressShipping());

        for (ShippingPolymorphismDemo.ShippingPolicy policy : policies) {
            ShippingPolymorphismDemo.ShippingQuote quote =
                    policy.quote(parcel);

            assertNotNull(quote);
            assertTrue(quote.getFeeVnd().signum() >= 0);
            assertTrue(quote.getEstimatedDays() > 0);
        }
    }
}
~~~

Additional tests should cover **boundary cases**: 1 g, 500 g, 501 g, 1.000 g, 1.001 g, inner-city/outer-city, `null`, and large values. The example uses `long` arithmetic to reduce overflow risk when adding weight units to constants.

To test `CheckoutService` independently of the pricing formula, use a fake `ShippingPolicy` implementation that returns a predetermined `ShippingQuote`. If `CheckoutService.estimate` returns the expected value and calls the policy correctly, orchestration honors the contract without depending on `ExpressShipping`.

## 11. Self-Check Questions with Answers

**1.** If `ShippingPolicy p = new ExpressShipping();`, which class supplies the formula for `p.quote(parcel)`?

**Answer:** `ExpressShipping`, because the runtime object is `ExpressShipping`. The `ShippingPolicy` variable type only controls which API can be called.

**2.** Does adding `SameDayShipping implements ShippingPolicy` require changes to `CheckoutService.estimate`?

**Answer:** Usually not, provided the new implementation honors the contract. The new strategy must be registered or selected in the appropriate configuration location; code calling `policy.quote(parcel)` stays unchanged.

**3.** A `class LegacyShipping` class has the same `quote(Parcel)` signature but does not `implements ShippingPolicy`. Can it be passed to the `CheckoutService(ShippingPolicy)` constructor?

**Answer:** Not under ordinary Java typing rules. Have the class implement the contract if its source can be changed, or use an appropriate adapter otherwise.

**4.** Why do `Printer.print(Object)` and `Printer.print(String)` illustrate overloading rather than runtime selection?

**Answer:** The compiler selects a signature based on the **static type of the argument** at the call site. It does not automatically select the `String` overload just because an `Object` reference points to a string.

**5.** Why might sharing a method name `quote` be insufficient to substitute implementations in an e-commerce system?

**Answer:** Valid type relationships and a shared semantic contract are required: input data, currency units, results, error rules, and side effects. If an implementation unexpectedly modifies `Parcel` or returns a negative fee, substitutability is broken.

**6.** For the 1.500 g inner-city parcel, why does the example quote 20.000 VND for economy, 25.000 VND for standard, and 95.000 VND for express?

**Answer:** Each policy uses different rates and weight increments despite accepting the same `Parcel` and returning the same `ShippingQuote`.

**7.** If a subclass has a `static` method sharing a name with a parent static method, is that runtime polymorphism?

**Answer:** No. This is method hiding; static calls are bound to the class name or expression type, not dynamically dispatched instance methods.

**8.** Can a `Map` or `switch` be used to select a policy based on the UI choice?

**Answer:** Yes. This is **the object-selection step**. Avoid repeating every policy's entire fee formula in every consuming component; delegate to `quote` instead.

## Conclusion

Polymorphism does not make objects identical; it allows **using them through the same contract** while each object retains its appropriate implementation.

For Java, remember this conceptual model:

**An interface or parent class defines "what can be requested" → concrete classes define "how to do it" → consuming code calls the shared method → runtime selects the implementation based on the actual object.**

When reading OOP code, look for a parent/interface-typed reference, an instance method call, and several classes that override or implement that method. That is often where polymorphism eliminates type-checking branches and makes the system more extensible.
