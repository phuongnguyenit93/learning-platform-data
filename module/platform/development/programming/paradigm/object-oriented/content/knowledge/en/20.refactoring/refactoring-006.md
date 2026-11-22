# Replacing Type-Based Conditionals with Polymorphism (Replace Conditional with Polymorphism) — Java OOP

## 1. The Problem: Why Are Many Type-Based Branches Hard to Maintain?

Suppose a sales application supports three delivery modes: STANDARD (regular delivery), EXPRESS (fast delivery), and PICKUP (customer collection). Each has different fee and delivery-time rules.

Initial implementations often inspect the type with a switch or chain of if/else conditions:

~~~java
switch (request.type) {
    case STANDARD: /* tính phí giao thường */ break;
    case EXPRESS:  /* tính phí giao nhanh */ break;
    case PICKUP:   /* tự nhận hàng */ break;
}
~~~

Such a block is not automatically a defect. Problems arise when **the same type-based decision** repeats across operations (fee calculation, delivery estimates, request processing, notification output), requiring edits in many places for each new type. Related branches are easily missed, and one class accumulates behavior for many variants.

**Replace Conditional with Polymorphism** is a refactoring technique that moves type-varying behavior into implementations of a shared contract. Callers ask an object to perform an operation, and Java selects the corresponding method through **dynamic dispatch**.

> The objective is to reorganize code **while preserving the observable contract**: valid inputs, results, exceptions, and promised side effects. Encountering a switch does not automatically justify a class hierarchy.

## 2. Comparing Structures Before and After

| Aspect | Type-based conditionals | Polymorphism |
|---|---|---|
| Behavior selection | Caller uses if/else, switch, or instanceof | Caller invokes a common method on an interface/superclass |
| Rule location | Numerous branches in one large class | Each implementation owns its rules |
| Adding a type | Edit each relevant switch | Add an implementation and register it at object selection/creation boundaries |
| Testing | One class contains many branches | Shared contract tests and tests for each variant |
| Extensibility | Easy to overlook branches | Depends on registration design and type structure |
| Cost | Fewer classes and simplicity with a few branches | More classes/objects and the need for a sensible interface |

This technique often supports the **Open/Closed Principle**: extend behavior through new implementations while limiting edits to stable business code. It does not eliminate type selection entirely: inputs may still contain type codes, which must be mapped to suitable objects at a boundary.

~~~mermaid
flowchart LR
    C["Client"] --> B["DeliveryService"]
    B --> P["DeliveryPolicy interface"]
    S["StandardPolicy"] -.-> P
    E["ExpressPolicy"] -.-> P
    K["PickupPolicy"] -.-> P
~~~

In this model, DeliveryService does not know each variant's fee formula. It only uses the DeliveryPolicy interface.

## 3. Runnable Java 11 Example: From Switch to Polymorphism

### Business Contract

An order has a nonnegative goods value (VND) and a positive integer weight (kg). Whole-kilogram weights are assumed to focus on refactoring rather than real-world measurements.

| Type | Shipping-fee rule | Estimated delivery days |
|---|---|---:|
| STANDARD | If order value is at least 500.000 VND: 0; otherwise: 20.000 + 5.000 × kg | 5 |
| EXPRESS | 45.000 + 10.000 × kg | 1 |
| PICKUP | 0 VND | 0 (customer collects the order) |

The service returns a DeliveryQuote containing feeVnd and etaDays. The legacy and refactored versions must produce **identical results** for all valid inputs without changing promised validation rules.

Save the complete program below in **DeliveryRefactoringDemo.java**. It uses Java 11 or later and requires neither Maven nor Spring nor a testing library.

~~~java
import java.util.Map;
import java.util.Objects;

public class DeliveryRefactoringDemo {
    enum DeliveryType {
        STANDARD, EXPRESS, PICKUP
    }

    static final class DeliveryRequest {
        final DeliveryType type;
        final long orderValueVnd;
        final int weightKg;

        DeliveryRequest(DeliveryType type,
                        long orderValueVnd,
                        int weightKg) {
            if (type == null || orderValueVnd < 0 || weightKg <= 0) {
                throw new IllegalArgumentException("Invalid delivery request");
            }
            this.type = type;
            this.orderValueVnd = orderValueVnd;
            this.weightKg = weightKg;
        }
    }

    static final class DeliveryQuote {
        final long feeVnd;
        final int etaDays;

        DeliveryQuote(long feeVnd, int etaDays) {
            this.feeVnd = feeVnd;
            this.etaDays = etaDays;
        }
    }

    // TRƯỚC: mọi quy tắc tính phí và thời gian ở một switch.
    static final class LegacyDeliveryService {
        DeliveryQuote quote(DeliveryRequest request) {
            Objects.requireNonNull(request, "request");

            switch (request.type) {
                case STANDARD:
                    long standardFee =
                            request.orderValueVnd >= 500_000L
                            ? 0L
                            : Math.addExact(20_000L,
                                  Math.multiplyExact(
                                      5_000L, (long) request.weightKg));
                    return new DeliveryQuote(standardFee, 5);

                case EXPRESS:
                    long expressFee = Math.addExact(45_000L,
                            Math.multiplyExact(
                                10_000L, (long) request.weightKg));
                    return new DeliveryQuote(expressFee, 1);

                case PICKUP:
                    return new DeliveryQuote(0L, 0);

                default:
                    throw new IllegalStateException("Unsupported type");
            }
        }
    }

    // SAU: một hợp đồng chung cho mọi loại giao hàng.
    interface DeliveryPolicy {
        DeliveryQuote quote(DeliveryRequest request);
    }

    static final class StandardPolicy implements DeliveryPolicy {
        @Override
        public DeliveryQuote quote(DeliveryRequest request) {
            long fee = request.orderValueVnd >= 500_000L
                    ? 0L
                    : Math.addExact(20_000L,
                          Math.multiplyExact(
                              5_000L, (long) request.weightKg));
            return new DeliveryQuote(fee, 5);
        }
    }

    static final class ExpressPolicy implements DeliveryPolicy {
        @Override
        public DeliveryQuote quote(DeliveryRequest request) {
            long fee = Math.addExact(45_000L,
                    Math.multiplyExact(
                        10_000L, (long) request.weightKg));
            return new DeliveryQuote(fee, 1);
        }
    }

    static final class PickupPolicy implements DeliveryPolicy {
        @Override
        public DeliveryQuote quote(DeliveryRequest request) {
            return new DeliveryQuote(0L, 0);
        }
    }

    // SAU: service điều phối, không chứa công thức theo loại.
    static final class DeliveryService {
        private final Map<DeliveryType, DeliveryPolicy> policies;

        DeliveryService(Map<DeliveryType, DeliveryPolicy> policies) {
            Objects.requireNonNull(policies, "policies");
            this.policies = Map.copyOf(policies);
            for (DeliveryType type : DeliveryType.values()) {
                if (!this.policies.containsKey(type)) {
                    throw new IllegalArgumentException(
                            "Missing policy for " + type);
                }
            }
        }

        DeliveryQuote quote(DeliveryRequest request) {
            Objects.requireNonNull(request, "request");
            // Đây là tra cứu chính sách, không phải các nhánh tính phí.
            DeliveryPolicy policy = policies.get(request.type);
            return policy.quote(request); // Dynamic dispatch
        }
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static void assertScenario(
            LegacyDeliveryService before,
            DeliveryService after,
            DeliveryRequest request,
            long expectedFee,
            int expectedDays) {

        DeliveryQuote oldQuote = before.quote(request);
        DeliveryQuote newQuote = after.quote(request);

        // Kiểm tra yêu cầu nghiệp vụ bằng kỳ vọng độc lập.
        check(oldQuote.feeVnd == expectedFee,
                "Old fee differs from requirement");
        check(oldQuote.etaDays == expectedDays,
                "Old ETA differs from requirement");
        check(newQuote.feeVnd == expectedFee,
                "New fee differs from requirement");
        check(newQuote.etaDays == expectedDays,
                "New ETA differs from requirement");

        // Đồng thời xác nhận hành vi cũ/sau refactor tương đương.
        check(oldQuote.feeVnd == newQuote.feeVnd,
                "Fee changed after refactoring");
        check(oldQuote.etaDays == newQuote.etaDays,
                "ETA changed after refactoring");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        LegacyDeliveryService before = new LegacyDeliveryService();

        DeliveryService after = new DeliveryService(Map.of(
                DeliveryType.STANDARD, new StandardPolicy(),
                DeliveryType.EXPRESS, new ExpressPolicy(),
                DeliveryType.PICKUP, new PickupPolicy()
        ));

        // Dưới ngưỡng: 20.000 + 5.000 × 2 = 30.000.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.STANDARD,
                                    499_999L, 2),
                30_000L, 5);

        // Đúng ngưỡng miễn phí.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.STANDARD,
                                    500_000L, 2),
                0L, 5);

        // Giao nhanh: 45.000 + 10.000 × 3 = 75.000.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.EXPRESS,
                                    100_000L, 3),
                75_000L, 1);

        // Tự đến lấy: không tính phí và không có ngày giao.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.PICKUP,
                                    0L, 1),
                0L, 0);

        // Các quy tắc dữ liệu không hợp lệ vẫn được giữ.
        expectInvalid(() ->
                new DeliveryRequest(DeliveryType.STANDARD, -1L, 1));
        expectInvalid(() ->
                new DeliveryRequest(DeliveryType.EXPRESS, 100L, 0));
        expectInvalid(() ->
                new DeliveryRequest(null, 100L, 1));

        System.out.println("4 scenarios + 3 invalid inputs: PASS");
    }
}
~~~

Compile and run in the file's directory:

~~~bash
javac DeliveryRefactoringDemo.java
java DeliveryRefactoringDemo
~~~

When all checks pass:

~~~text
4 scenarios + 3 invalid inputs: PASS
~~~

The program deliberately verifies behavior **in two ways**: comparing before/after results and comparing them against independent business expectations. Comparing versions alone is insufficient because both could implement the same incorrect formula.

### What Changed, and What Remained the Same?

| Concern | Before refactoring | After refactoring |
|---|---|---|
| Standard-delivery formula | STANDARD branch in LegacyDeliveryService | StandardPolicy.quote |
| Express-delivery formula | EXPRESS branch | ExpressPolicy.quote |
| Customer pickup | PICKUP branch | PickupPolicy.quote |
| Policy selection | Switch on enum | Map from enum → DeliveryPolicy |
| Variant-specific execution | Execute the selected branch | Call policy.quote; JVM selects implementation |
| Free-shipping threshold at 500.000 | Unchanged | Unchanged |
| Results and input-validation rules | Original contract | Unchanged |

### Why Is This Polymorphism?

The policy variable has type **DeliveryPolicy**, but the actual object may be StandardPolicy, ExpressPolicy, or PickupPolicy. Calling policy.quote(request) causes the JVM to execute the overriding method on the concrete class. DeliveryService need not know which formula runs.

This is **runtime polymorphism** through an interface and method overriding, not merely a switch rewritten as three private methods. If all three formulas stay in one class with enum-based branching, type-specific behavior has not been distributed to objects.

## 4. Refactoring Steps for a Real Project

1. **Locate type-based conditions.** Find branches examining the same discriminator, such as an enum, string code, or instanceof. Determine which branches represent the same kind of behavior.
2. **Write characterization tests.** Record current results for important inputs: common and rare types, price thresholds, failures, and meaningful side effects.
3. **Extract a shared contract.** For example, DeliveryPolicy.quote(request). Name methods after business responsibilities rather than creating an interface simply to hide a switch.
4. **Extract per-type implementations.** Move formulas and variant-specific logic into StandardPolicy, ExpressPolicy, and PickupPolicy one at a time, compiling and testing after each move.
5. **Centralize implementation selection.** Use a factory, DI container, or Map registry at the object creation/selection boundary. Business code receives or looks up DeliveryPolicy only.
6. **Remove obsolete conditionals.** Avoid maintaining the old switch alongside the new policy system for long, because their behavior can diverge.
7. **Run regression and integration tests.** Validate results, exceptions, collaborator contracts, transactions, and external resources where the real application uses them.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as DeliveryService
    participant R as Registry
    participant P as DeliveryPolicy cụ thể
    C->>S: quote(request)
    S->>R: get(request.type)
    R-->>S: policy
    S->>P: quote(request)
    P-->>S: DeliveryQuote
    S-->>C: DeliveryQuote
~~~

## 5. Choosing Interfaces, Abstract Classes, Subclasses, or Strategy

**Interface + implementation**, as in the example, suits variants with a shared contract but different formulas and little common state/behavior to inherit.

**Abstract class + subclass** fits when genuine shared invariants and default processing steps exist, such as common input validation. Avoid moving too much conditional logic back into the base class.

**Strategy pattern (favoring composition)** fits when behavior is selected by configuration or changes at runtime rather than being intrinsic to an entity's type. STANDARD/EXPRESS/PICKUP are delivery policies chosen per request, so they do not necessarily require Order subclasses.

**Enum constants with their own methods** are another form of polymorphism in Java:

~~~java
enum SimpleDelivery {
    STANDARD {
        @Override long fee(int kg) {
            return 20_000L + 5_000L * kg;
        }
    },
    EXPRESS {
        @Override long fee(int kg) {
            return 45_000L + 10_000L * kg;
        }
    };

    abstract long fee(int kg);
}
~~~

This short example **illustrates syntax**, not the full fee contract in section 3 (it omits value-based free shipping, input validation, and overflow handling). Enum-specific methods work well for fixed variants with short logic. Complex policies, external dependencies, or module-level registration of new implementations often favor separate Strategy classes for flexibility and testing.

## 6. Common Mistakes

| Mistake | Why it misses the goal | How to address it |
|---|---|---|
| Creating an interface while the service still switches on types to call concrete classes | Callers still know details and require branch edits | Move selection into a factory/registry and call a shared contract |
| Using instanceof and casting for every variant | Subtype coupling remains | Invoke polymorphic methods; retain type checks only when truly needed at boundaries |
| Every policy inspects request.type before deciding what to do | Conditions are duplicated across classes | Let the registry select policies; each policy handles its own rule |
| Adding a huge superclass to share unrelated details | High coupling; changes to the parent affect all types | Extract a concise abstraction and favor composition |
| Moving code while changing business formulas | Behavior preservation becomes hard to prove | Refactor and change policies in separately tested steps |
| Adding a subtype but forgetting registry registration | Runtime failure on the new type | Test complete registration and fail fast at startup |
| Treating every switch as a code smell | Many classes for simple, stable conditions | Keep a switch when it remains clear and rarely changes |
| Testing only that a policy method was called once | Does not prove shipping fees are correct | Assert feeVnd, etaDays, and independent boundary cases |

### Can New Types Be Added Without Editing Any Existing Code?

Not absolutely. With the example's enum and Map architecture, adding SAME_DAY still requires defining an enum constant, creating SameDayPolicy, and registering it in the Map. The important point is that **DeliveryService.quote needs no new formula or branch**. If requirements call for dynamic plugin registration, a DI container/factory may discover implementations, at the cost of configuration, duplicate checks, and missing-policy handling.

### Should Variant-Specific Fields Enter the Shared Interface?

Do not force every variant to hold unused fields merely for uniformity. If each type needs very different input, consider specialized requests, behavioral abstractions, or explicit validation boundaries. Interfaces should express real common capabilities, not methods that implementations must override only to throw UnsupportedOperationException.

### Concerns with Stateful Objects

The example's policies are stateless and can be shared safely. If an implementation writes mutable fields while serving multiple requests, consider object lifetime, thread safety, and synchronization. Refactoring must not accidentally turn per-request state into shared singleton state.

## 7. Testing to Prove Behavior Has Not Changed

Replacing switches with polymorphism must not lose boundary cases. Test at these levels:

- **DeliveryService contract tests:** Each type returns correct fees and ETA; STANDARD handles the 499.999/500.000 threshold; invalid inputs are rejected; new types are fully registered.
- **Per-policy unit tests:** Focus on each formula and overflow. For example, ExpressPolicy.quote with large weights must use exact long arithmetic or throw ArithmeticException on overflow.
- **Integration tests for external systems:** Verify that the factory/DI selects the correct policy and that real adapters perform payment/delivery requests in a controlled testing environment.

Example JUnit 5 tests for the standard-delivery boundary (assuming the program above resides in the same package):

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StandardPolicyTest {
    @Test
    void freeShippingAppliesAtThreshold() {
        DeliveryRefactoringDemo.DeliveryPolicy policy =
                new DeliveryRefactoringDemo.StandardPolicy();

        var below = policy.quote(
                new DeliveryRefactoringDemo.DeliveryRequest(
                    DeliveryRefactoringDemo.DeliveryType.STANDARD,
                    499_999L, 2));

        var atThreshold = policy.quote(
                new DeliveryRefactoringDemo.DeliveryRequest(
                    DeliveryRefactoringDemo.DeliveryType.STANDARD,
                    500_000L, 2));

        assertEquals(30_000L, below.feeVnd);
        assertEquals(5, below.etaDays);
        assertEquals(0L, atThreshold.feeVnd);
        assertEquals(5, atThreshold.etaDays);
    }
}
~~~

Use JUnit Jupiter in the test scope to run the example. Note that policy.quote receives DeliveryRequest containing a type to illustrate an existing-system contract, but StandardPolicy does not inspect that field; DeliveryService selects the correct policy by type. A mature design might pass only the data each policy needs, avoiding the impression that policies must always check the enum.

## 8. When Should You NOT Apply This Refactoring?

A short switch in **one place** for classifying status codes, logging, or simple mappings is often easier to understand than an entire hierarchy. For a fixed set of types whose behavior rarely changes, the cost of interfaces, factories, and files may exceed their benefits.

Likewise, do not replace checks based on **values or state** with subtypes merely because they use if. For instance, the free-shipping threshold (orderValueVnd >= 500.000) is a rule **inside StandardPolicy**, not a new delivery type. Polymorphism selects *families of behavior* by type; business conditions inside each variant can and should remain.

Before refactoring, ask three questions:

1. Does the condition recur across behaviors and often require synchronized updates?
2. Do variants share a contract clear enough for callers to use without knowing concrete classes?
3. Can existing tests protect results, failures, and side effects when code moves to different implementations?

If all three answers are yes, Replace Conditional with Polymorphism often provides substantial value.

## 9. Exercises

**Exercise 1 — Add SAME_DAY:** Assume same-day delivery costs 80.000 + 12.000 × kg with ETA = 0 days (within the day). Add DeliveryType.SAME_DAY, implement SameDayPolicy, and register it. Write independent tests for the exact formula without adding a branch to DeliveryService.quote.

**Exercise 2 — Detect regressions:** Deliberately change the STANDARD free-shipping rule to greater than 500.000 instead of greater than or equal to. Run the program; the case exactly at 500.000 must fail.

**Exercise 3 — Recognize duplicated conditions:** If another class switches on DeliveryType to format a service description, consider including display names in DeliveryPolicy. Explain when adding formatting responsibilities to a policy would reduce cohesion and propose a separate collaborator if appropriate.

**Exercise 4 — Verify registration:** Remove one policy from the Map and confirm that the DeliveryService constructor rejects incomplete configuration with IllegalArgumentException before accepting requests.

**Exercise 5 — Choose a technique:** For four status codes that only change the color of a UI label, compare one short switch with four classes. Choose the less complex approach and explain why polymorphism is not always beneficial.

## 10. Key Takeaways

**Replace Conditional with Polymorphism** moves type-dependent behavior to the objects responsible for it. Callers use a common contract, and Java dispatches to the right implementation. This is **refactoring**, so behavior must be preserved; do not confuse architectural restructuring with changing business policy. Choose polymorphism when it genuinely reduces repeated branches, improves cohesion, lowers coupling, and enables controlled extension.
