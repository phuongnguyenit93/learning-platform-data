# Overusing casts and type checks in OOP: when should you use polymorphism?

> **Topic:** OOP → Design Pitfalls → Overusing casts and type checks.  
> **Objective:** Recognize code smells caused by repeated `instanceof`, downcasts, or class-name comparisons; distinguish necessary type validation from designs coupled to concrete classes; learn to refactor toward polymorphism/composition, validate data boundaries in Java 17, and test without unintentionally changing behavior.

## 1. Code that "knows too much" about object types

Suppose an application calculates shipping fees for two options: economy and express. Both represent shipping choices, but the order-processing class asks **which concrete class the object belongs to**:

~~~java
// Minh họa lỗi thiết kế; các lớp EconomyOption/ExpressOption
// và hàm calculate... được giả định đã định nghĩa.
long fee(DeliveryOption option, DeliveryRequest request) {
    if (option instanceof EconomyOption) {
        EconomyOption economy = (EconomyOption) option;
        return 12_000L + 2_500L * request.distanceKm();
    } else if (option instanceof ExpressOption) {
        ExpressOption express = (ExpressOption) option;
        return 25_000L + 4_500L * request.distanceKm();
    }
    throw new IllegalArgumentException("Unknown option");
}
~~~

This is a *type-checking conditional*: the caller chooses the business algorithm by examining the object's subtype and then implements the formula itself. The `economy`/`express` variables are not even used; the casts are unnecessary.

If a quotation screen, controller, and batch job all repeat the same branches, adding a third shipping type requires modifying multiple places. Extensibility depends on finding every scattered `instanceof`. **That is the design smell**; the `instanceof` operator itself is not forbidden.

A useful code-review question:

> *Does the caller need to know an object's concrete class to choose behavior that the object itself could own?*

If the answer is "yes," consider moving that behavior into an abstraction and using **polymorphism**.

## 2. Understanding casts and type checks in Java

Java is a **statically typed** language, but a reference typed as a superclass/interface can point to a concrete subtype object. Distinguish:

| Concept | Meaning | Example |
|---|---|---|
| **Static type** | Expression/variable type known to the compiler | `Animal animal` |
| **Runtime class** | The class of the referenced object | `new Dog()` |
| **Upcasting** | Using a subtype where a supertype is expected (often with no explicit cast) | `Animal a = new Dog();` |
| **Downcasting** | Asking to treat a broadly typed reference as a narrower type | `Dog d = (Dog) a;` |
| **`instanceof`** | Tests whether a reference matches a type/pattern at runtime | `a instanceof Dog` |
| **Dynamic dispatch** | Chooses the overridden instance-method implementation at runtime | `a.sound()` invokes `Dog.sound()` |

Java 17 example:

~~~java
interface Animal {
    String sound();
}

final class Dog implements Animal {
    @Override
    public String sound() { return "Gâu"; }

    String fetch() { return "Nhặt bóng"; }
}

final class Cat implements Animal {
    @Override
    public String sound() { return "Meo"; }
}

Animal animal = new Dog(); // Upcast: hợp lệ, không mất đối tượng Dog.
System.out.println(animal.sound()); // "Gâu" nhờ overriding.

// animal.fetch(); // Lỗi biên dịch: Animal không công bố fetch().
if (animal instanceof Dog dog) {
    System.out.println(dog.fetch()); // Pattern matching Java 17.
}
~~~

`animal` still has **static type `Animal`**, while the actual object is a `Dog`. Upcasting does not cut the Dog portion off an object. But code knowing only the Animal interface cannot call Dog-specific methods unless it checks and narrows the type or redesigns the API.

### A downcast can be syntactically valid but fail at runtime

~~~java
Animal animal = new Cat();

// Compiler có thể chấp nhận phép cast từ Animal xuống Dog,
// nhưng đối tượng thật là Cat:
Dog dog = (Dog) animal; // ClassCastException khi chạy.
~~~

`(Dog) animal` does not turn a `Cat` into a `Dog`. A reference cast merely asks the JVM to check whether the existing object matches the target type. `instanceof Dog` can guard subtype-specific behavior, but **a successful type check does not itself imply good design**.

## 3. Common forms of overuse

| Symptom | Why it is suspicious | Better direction |
|---|---|---|
| `if (animal instanceof Dog) ... else if (animal instanceof Cat)` repeated in many places | Callers decide behavior instead of the subtypes | Move shared behavior into an interface and override it |
| `((ConcreteRepo) repository).specialSave(...)` | Caller depends on a concrete implementation hidden behind an interface | Revisit the necessary contract or separate a clear capability |
| Comparing `obj.getClass() == Dog.class` to select logic | Coupled to an exact class; excludes subclasses/proxies | Prefer polymorphism; require an exact class only when specified |
| Repeated casts from `Object` in business services | Type contracts were discarded too early | Generics, typed DTOs, and boundary adapters |
| Widespread `@SuppressWarnings("unchecked")` | Hides evidence of unchecked type safety | Isolate legacy APIs, validate, or move to typed APIs |
| Repeated `switch(typeCode)` with per-type formulas | Type codes control behavior instead of objects | Strategy/polymorphism or capability-based organization |
| `catch (ClassCastException)` to try subtypes | Exceptions substitute for type modeling | Check at boundaries and avoid speculative downcasts |

**Not every example in the table is necessarily wrong.** A single `switch` selecting an implementation from configuration may be quite clear; using `instanceof` to validate untrusted input is reasonable. The issue is the **frequency, location, and responsibility** of type checks.

## 4. Focused refactoring: polymorphism for shipping algorithms

Instead of making `Checkout` inspect subtypes and contain every shipping formula, use an interface describing the necessary behavior:

~~~mermaid
flowchart LR
    caller["Client / composition root"] --> checkout["ShippingCheckout"]
    checkout --> port["ShippingPolicy"]
    economy["EconomyShipping"] -.->|implements| port
    express["ExpressShipping"] -.->|implements| port
    caller -.->|chọn implementation| economy
    caller -.->|chọn implementation| express
~~~

The dependency direction matters: **`ShippingCheckout → ShippingPolicy ← Concrete Shipping`**. The caller selects a strategy when constructing objects; the Checkout pricing code need not know subtype names. Strategy selection can belong in configuration, a DI container, or a dedicated policy-selection point.

### Complete Java 17 example that compiles and runs

Assumptions for the demo:

- Order IDs consist only of `A-Z`, digits, and hyphens.
- Integer distances range from **1–1000 km**.
- Integer weights range from **1–20.000 g**.
- Fees use **kilograms rounded up**, avoiding decimal money values to keep the example focused on design.
- Fee amounts are **integer VND**; the formulas below are simulated values, not real shipping tariffs.

Save all the code in **`CastRefactorDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;

enum DeliveryTier {
    ECONOMY, EXPRESS
}

record DeliveryRequest(
        String orderId,
        int distanceKm,
        int weightGrams
) {
    DeliveryRequest {
        Objects.requireNonNull(orderId, "orderId");

        if (!orderId.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid orderId");
        }
        if (distanceKm < 1 || distanceKm > 1_000) {
            throw new IllegalArgumentException("Distance outside 1..1000");
        }
        if (weightGrams < 1 || weightGrams > 20_000) {
            throw new IllegalArgumentException("Weight outside 1..20000");
        }
    }

    int roundedKilograms() {
        // Chặn trên từ record constructor khiến phép cộng an toàn.
        return (weightGrams + 999) / 1_000;
    }
}

// Hợp đồng hành vi: cách tính phí, không yêu cầu caller biết subtype.
interface ShippingPolicy {
    long feeVnd(DeliveryRequest request);
}

final class EconomyShipping implements ShippingPolicy {
    @Override
    public long feeVnd(DeliveryRequest request) {
        Objects.requireNonNull(request);
        return 12_000L
                + 2_500L * request.distanceKm()
                + 2_000L * request.roundedKilograms();
    }
}

final class ExpressShipping implements ShippingPolicy {
    @Override
    public long feeVnd(DeliveryRequest request) {
        Objects.requireNonNull(request);
        return 25_000L
                + 4_500L * request.distanceKm()
                + 5_000L * request.roundedKilograms();
    }
}

record ShippingQuote(String orderId, long feeVnd) {
    ShippingQuote {
        Objects.requireNonNull(orderId, "orderId");
        if (feeVnd < 0) {
            throw new IllegalArgumentException("Negative shipping fee");
        }
    }
}

final class ShippingCheckout {
    private final ShippingPolicy policy;

    ShippingCheckout(ShippingPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    ShippingQuote quote(DeliveryRequest request) {
        Objects.requireNonNull(request, "request");
        return new ShippingQuote(
                request.orderId(), policy.feeVnd(request));
    }
}

public class CastRefactorDemo {
    public static void main(String[] args) {
        // Chọn implementation ở composition root, không chọn bằng
        // instanceof/downcast bên trong ShippingCheckout.
        Map<DeliveryTier, ShippingPolicy> policies = Map.of(
                DeliveryTier.ECONOMY, new EconomyShipping(),
                DeliveryTier.EXPRESS, new ExpressShipping()
        );

        DeliveryRequest request =
                new DeliveryRequest("ORD-7", 4, 1_500);

        for (DeliveryTier tier : DeliveryTier.values()) {
            ShippingPolicy selected = policies.get(tier);
            ShippingCheckout checkout = new ShippingCheckout(selected);

            ShippingQuote quote = checkout.quote(request);
            System.out.println(
                    tier + " -> " + quote.feeVnd() + " VND");
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac CastRefactorDemo.java
java CastRefactorDemo
~~~

Output:

~~~text
ECONOMY -> 26000 VND
EXPRESS -> 53000 VND
~~~

Manually verify a distance of **4 km** and a weight of **1.500 g** (rounded up to **2 kg**):

| Policy | Example formula | Fee |
|---|---|---:|
| Economy | 12.000 + 2.500 × 4 + 2.000 × 2 | 26.000 VND |
| Express | 25.000 + 4.500 × 4 + 5.000 × 2 | 53.000 VND |

Note that `DeliveryRequest` **restricts input ranges** so the `long` multiplication/addition operations cannot overflow within the demo. Real applications with larger ranges or externally supplied formulas must explicitly guard against overflow (for example with `Math.multiplyExact`, `Math.addExact`, or a suitable money type).

### Why does this refactoring actually solve the problem?

Initially, **the caller owns both the subtype selection and every pricing formula**. After refactoring:

1. `ShippingPolicy` defines **one shared capability**: calculating a fee for a `DeliveryRequest`.
2. Each implementation owns **its own formula**.
3. `ShippingCheckout` orchestrates policy calls and returns results. It needs no `instanceof`, casts, `getClass()`, or `switch` on classes.
4. The `Map<DeliveryTier, ShippingPolicy>` in `main` is merely **the policy-selection point**, not business logic scattered throughout the application.
5. Adding `SameDayShipping` mostly requires implementing and registering it; `ShippingCheckout.quote()` stays unchanged.

**Switching to polymorphism does not guarantee correct results.** Each implementation must still honor its contract, such as returning a nonnegative fee without surprising side effects for a pure quotation operation. `ShippingQuote` rejects negative fees; tests must also verify formulas.

## 5. Comparing the execution paths before and after refactoring

~~~mermaid
flowchart TB
    subgraph Before["Trước: caller phải phân loại"]
      B0["Checkout nhận DeliveryOption"] --> B1{"instanceof ?"}
      B1 -->|Economy| B2["downcast / công thức Economy"]
      B1 -->|Express| B3["downcast / công thức Express"]
      B1 -->|khác| B4["Unsupported type"]
    end

    subgraph After["Sau: chọn policy và ủy quyền"]
      A0["Composition root chọn policy"] --> A1["Checkout nhận ShippingPolicy"]
      A1 --> A2["policy.feeVnd(request)"]
      A2 --> A3["JVM dispatch tới implementation"]
    end
~~~

When many places need to "do X differently for each Y type," repeated `instanceof` may indicate **a missing behavior X in Y's contract**. Yet every branch need not become a base-class method: decide whether the behavior truly belongs to Y or to a different service or structure.

## 6. When is `instanceof` the right choice?

### 6.1. Validating data at an untrusted boundary

If a legacy library or API supplies `Object` or `List<?>` values, **validate the data shape before entering a strongly typed domain**. This protects a type contract; it is different from scattering business branches.

For example, extract a list of string labels from an uncertain object:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class InputParser {
    static List<String> requireTags(Object input) {
        // Java 17: pattern matching for instanceof.
        if (!(input instanceof List<?> rawTags)) {
            throw new IllegalArgumentException("Expected a list");
        }

        List<String> tags = new ArrayList<>();
        for (Object raw : rawTags) {
            if (!(raw instanceof String tag) || tag.isBlank()) {
                throw new IllegalArgumentException(
                        "Expected nonblank String element");
            }
            tags.add(tag);
        }

        return List.copyOf(tags);
    }
}
~~~

Example usage:

~~~java
List<String> tags = InputParser.requireTags(
        List.of("java", "oop")); // ["java", "oop"]

// InputParser.requireTags(List.of("java", 42));
// Ném IllegalArgumentException, không cố ép cả List thành List<String>.
~~~

This converts an *Object → typed value*. Afterward, business logic accepts `List<String>` and **does not need to recheck each element** unless raw/unchecked operations violate the contract. `List.copyOf` returns a collection that cannot be mutated through its API and does not follow changes in the source, but it is not a deep copy for mutable elements; here, `String` is immutable.

### 6.2. A subtype truly offers an optional capability

~~~java
interface Printable {
    void print();
}

interface Scannable {
    void scan();
}

void useDevice(Printable device) {
    device.print();

    if (device instanceof Scannable scanner) {
        scanner.scan();
    }
}
~~~

In this simulated example, scanning is an **optional capability** distinct from printing. Checking for `Scannable` may be more appropriate than requiring every `Printable` to implement `scan()` and throw `UnsupportedOperationException`. This need not be a design smell if the optional behavior is genuinely required. Conversely, if callers constantly check for `Scannable`, consider requesting a `Scannable` object in the API from the outset.

### 6.3. A closed data family processed externally

An operation such as **rendering reports** for an AST/expression structure with several variants may need to classify nodes in one centralized place. When the set of subtypes is **closed and controlled**, Java 17 offers `sealed interface` and `instanceof` patterns; this can be reasonable if nodes should not know about every output format.

~~~java
sealed interface Expr permits Literal, Sum {}

record Literal(int value) implements Expr {}

record Sum(Expr left, Expr right) implements Expr {}

static int evaluate(Expr expr) {
    if (expr instanceof Literal literal) {
        return literal.value();
    }
    if (expr instanceof Sum sum) {
        return Math.addExact(
                evaluate(sum.left()), evaluate(sum.right()));
    }
    throw new IllegalStateException("Unexpected Expr: " + expr);
}
~~~

This illustrates Java 17 with an `evaluate` method declared inside a class. `Sum` supports complex expression trees; `Math.addExact` reports overflow beyond `int`. A `sealed` hierarchy limits expression types, keeping dispatch centralized and testable.

Crucially, **type patterns in `switch` were still a preview feature in Java 17**, and should not be presented as an unflagged Java 17 feature. This code uses only `instanceof` pattern matching and compiles with a standard JDK 17. Newer Java versions offer other pattern-switch options.

**Visitor/type-dispatch trade-off:** If new *data types* are added frequently, methods on interfaces/subclasses may be easier to extend; if new *operations* are regularly added to a relatively closed data family, a visitor or separate processor may fit better. Choose based on real change patterns rather than eliminating every type check at all costs.

## 7. Downcasting to implementations: why it undermines abstraction

Consider a service receiving a repository through an interface:

~~~java
interface OrderRepository {
    void save(String id);
}

final class JdbcOrderRepository implements OrderRepository {
    @Override
    public void save(String id) { /* ... */ }

    void flushJdbcBatch() { /* ... */ }
}

void process(OrderRepository repository) {
    repository.save("ORD-1");

    // Code smell nếu caller mặc định repo luôn là JDBC:
    ((JdbcOrderRepository) repository).flushJdbcBatch();
}
~~~

Passing an in-memory repository or mock could make `process` throw `ClassCastException`. Even with `if (repository instanceof JdbcOrderRepository jdbc)`, the service knows JDBC details and behavior becomes inconsistent across adapters.

Possible fixes depend on intent:

- If `flush` belongs in the contract **every repository must honor**, add it to the abstraction deliberately.
- If flushing is merely a JDBC optimization, **keep it inside the adapter** so callers need not know.
- For an **optional capability**, define a separate capability interface and require it only where appropriate.
- If a workflow intentionally supports only JDBC, declare `JdbcOrderRepository` explicitly at the boundary instead of advertising a false polymorphic interface.

**Do not** add a method to an interface merely to avoid `instanceof` when it is inappropriate for other implementations; that can violate the Interface Segregation Principle or Liskov Substitution Principle.

## 8. Overusing casts in generics and collections

Java generics prevent many compile-time errors. Preserve type information through APIs:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> codes = new ArrayList<>();
codes.add("ORD-1");

// codes.add(100); // Lỗi compile time: 100 không phải String.
String first = codes.get(0);
~~~

Raw types can bypass these protections:

~~~java
List<String> codes = new ArrayList<>();
List raw = codes; // Raw type, compiler phát cảnh báo.
raw.add(123);     // Unchecked call, không an toàn.

// Có thể ném ClassCastException ở đây:
String code = codes.get(0);
~~~

A commonly attempted but incorrect "fix" is:

~~~java
// KHÔNG NÊN: Cast này không kiểm tra từng phần tử của list.
// List<String> names = (List<String>) (List<?>) unknownList;
~~~

Due to **type erasure**, Java cannot check at runtime that an object is `List<String>` using `instanceof List<String>`. `instanceof List<?>` only establishes "this is a List with unknown type arguments"; validate its elements by iterating as in `InputParser.requireTags`.

| Situation | Better approach |
|---|---|
| Method returns `Object` but always contains `User` | Return `User` in its signature, or `Optional<User>` if absence is possible |
| Registry stores objects of multiple types | Use a checked typed-key/`Class<T>` API |
| Legacy API requires raw `List` | Convert/validate once in an adapter; expose typed APIs thereafter |
| Repeated subtype casts to access methods | Move common behavior into an interface or suitable capability |
| Cast merely "to silence the compiler" | Find why type information was lost instead of hiding warnings |

### When `Class<T>.cast` is appropriate

An adapter may know `Class<T>` from configuration but receive only `Object` from a dynamic API. It can check the provided type token:

~~~java
final class TypedBoundary {
    static <T> T require(Object value, Class<T> expected) {
        if (!expected.isInstance(value)) {
            throw new IllegalArgumentException(
                    "Expected " + expected.getName());
        }
        return expected.cast(value);
    }
}

String text = TypedBoundary.require("hello", String.class);
~~~

`Class.cast` only checks **compatible runtime classes**. It cannot turn `List.class` into a validator for `String` elements and cannot guarantee values obey domain rules (nonempty strings, valid IDs, authorization).

## 9. Confusing type checks with state checks

Many `instanceof` branches actually try to answer a **state** question, not a class-type question. For example:

~~~java
if (order instanceof PaidOrder) {
    ship(order);
}
~~~

This can be reasonable if `PaidOrder` is a distinct type and the entire system implements safe *typestate*. More often, state is a business attribute or invariant such as `OrderStatus.PAID`. Do not create `CreatedOrder`, `PaidOrder`, and `CancelledOrder` subtypes solely to replace every enum if objects change state during their lifecycle and the application then requires difficult cross-casting.

Distinguish these questions:

| Real question | Preferred technique |
|---|---|
| How does an object perform its own behavior? | Polymorphism/Strategy |
| Does untrusted data have the expected type? | `instanceof`/type token/validation at the boundary |
| What business state is an order in? | State model, domain methods, or an enum with guarded transitions |
| Does the client need an optional capability? | Capability interface or clear contract |
| Must a framework load a plugin selected at runtime? | Registry/factory and centralized type checking |
| Are multiple operations needed over a closed data family? | Visitor/central dispatch/sealed hierarchy based on change patterns |

Casting is often overused because **the API does not express what callers really need**, not merely due to a syntax problem.

## 10. Testing after refactoring: contracts matter more than class names

Test that `ShippingCheckout` uses the same contract with any implementation, without branching on concrete classes.

JUnit Jupiter 5 example in the same package as `CastRefactorDemo.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ShippingCheckoutTest {
    private static final DeliveryRequest REQUEST =
            new DeliveryRequest("ORD-7", 4, 1_500);

    @Test
    void economyAndExpressFollowTheirOwnAlgorithms() {
        ShippingQuote economy = new ShippingCheckout(
                new EconomyShipping()).quote(REQUEST);
        ShippingQuote express = new ShippingCheckout(
                new ExpressShipping()).quote(REQUEST);

        assertEquals(26_000L, economy.feeVnd());
        assertEquals(53_000L, express.feeVnd());
        assertEquals("ORD-7", economy.orderId());
    }

    @Test
    void anotherImplementationWorksWithoutCast() {
        ShippingPolicy promotional = request -> 0L;

        ShippingQuote quote =
                new ShippingCheckout(promotional).quote(REQUEST);

        assertEquals(0L, quote.feeVnd());
    }

    @Test
    void invalidRequestIsRejectedBeforePricing() {
        assertThrows(IllegalArgumentException.class,
                () -> new DeliveryRequest("ORD-7", 0, 1_500));
        assertThrows(IllegalArgumentException.class,
                () -> new DeliveryRequest("ORD-7", 4, -1));
    }

    @Test
    void policyBreakingTheNonnegativeContractIsRejected() {
        ShippingPolicy broken = request -> -100L;

        assertThrows(IllegalArgumentException.class,
                () -> new ShippingCheckout(broken).quote(REQUEST));
    }
}
~~~

These tests need the `org.junit.jupiter:junit-jupiter` dependency and a suitable JUnit runner. The second test uses a **lambda** because `ShippingPolicy` is a functional interface (one abstract method), showing that the Context does not care whether the object is `EconomyShipping`/`ExpressShipping`.

### Additional shared contract tests

As implementation counts grow, apply the same contract-test suite to every policy:

- For valid requests, results are nonnegative and there are no unexpected side effects.
- Given the same input and stable configuration, results are predictable under the contract.
- Test distance and weight boundaries, including kilogram rounding.
- Each variant has specific expected values, not just `fee >= 0`.

**Do not confuse these claims:** passing unit tests does not prove all real-world cases. If fee policies depend on databases, exchange rates, time-dependent rules, or networks, add appropriate integration tests.

## 11. Choosing a refactoring technique according to change patterns

There is no single solution for every `if (x instanceof Y)` tree:

| Current design | Refactoring approach | Reason |
|---|---|---|
| Callers branch on subtypes to perform **the same behavior** | **Replace Conditional with Polymorphism** | Behavior belongs to the responsible object |
| Each type has its own algorithm, selected at runtime | **Strategy + DI/composition** | Swap behavior without exposing concrete classes to Context |
| Only one place branches to construct an implementation | Factory/registry or a `switch` at the composition root | Centralized selection stays out of business logic |
| An `Object` block from a legacy API | **Boundary parser/adapter** | Validate once, then use typed values |
| Many operations on a closed set of data types | Visitor/central dispatch | Avoid putting unnatural behaviors into the data type |
| An extra capability is not supported by every subtype | Separate capability interface | Do not force implementations to provide meaningless methods |

**SOLID note:** Replacing conditionals with polymorphism may support OCP and DIP, but **LSP** still matters: every implementation must satisfy the shared contract. An interface whose implementation repeatedly throws `UnsupportedOperationException` may only hide a conditional behind poor abstraction.

### Refactoring a running codebase

1. **List type-check sites:** locate `instanceof`, downcasts, `getClass()`, and `switch` statements driven by type codes. Decide whether they check a type, capability, state, or format.
2. **Capture behavior:** test values, failure paths, side effects, ordering, and "unsupported type" cases before editing. Preserve required exceptions.
3. **Define a genuine shared contract:** name methods for domain needs and specify inputs/outputs, null policies, and failure modes.
4. **Move behavior to its owner:** override in subtypes or wrap algorithms in independent Strategies; keep infrastructure concerns out of domain objects.
5. **Limit selection points:** let a composition root/registry receive type codes from configuration and supply implementations.
6. **Remove redundant branches/casts:** delete branches replaced by dispatch; explain any remaining casts.
7. **Verify changes with tests:** run relevant unit and integration tests; monitor performance/GC if dispatch changes on hot paths.
8. **Reevaluate simplicity:** if new classes cost more than the refactoring helps, a small, centralized, stable conditional may be preferable.

## 12. When should you NOT refactor every `instanceof`?

Do not insist that "good OOP contains absolutely no `instanceof`." These scenarios can be legitimate:

- Parse untrusted plugin/JSON/legacy API data and validate its type before constructing domain objects.
- Use pattern matching over a `sealed` hierarchy in **one** intentional parser/interpreter.
- Detect optional capabilities the base interface should not be forced to support.
- Implement infrastructure such as serializers, persistence adapters, middleware, or debuggers, where classifying data is the primary task.
- Select an implementation once from enum/config at the composition root; one `switch` does not violate OOP.

Conversely, if 15 places must know `Dog`, `Cat`, and `Bird` just to invoke "make sound," there is a real design problem. **Evaluate coupling and change risk** rather than enforcing a syntactic ban.

## 13. Practice exercise: replacing type checks with polymorphism

A system supports these document types:

~~~java
interface Document {}

final class PdfDocument implements Document {
    final int pages;
    PdfDocument(int pages) { this.pages = pages; }
}

final class TextDocument implements Document {
    final int characters;
    TextDocument(int characters) { this.characters = characters; }
}

class DocumentAnalyzer {
    int workload(Document document) {
        if (document instanceof PdfDocument pdf) {
            return pdf.pages * 5;
        }
        if (document instanceof TextDocument text) {
            return text.characters / 100;
        }
        throw new IllegalArgumentException("Unsupported document");
    }
}
~~~

Requirements:

1. Identify the **type-checking branches** and explain why `DocumentAnalyzer` depends on two implementations.
2. Move appropriate behavior to the `Document.workload()` contract or introduce a `WorkloadStrategy`; explain the choice.
3. Add `SpreadsheetDocument` with a new workload calculation without changing the existing caller.
4. Validate `pages` and `characters`; avoid overflow in `pages * 5` when input is large.
5. Write unit tests for all three types and one test calling `analyzer.workload(document)` through the shared interface.
6. Extend the problem: if 10 more independent analyses are added for three document types, explain why a visitor/separate operation might be better than adding 10 methods to `Document`.
7. Give a case where `instanceof` remains valid in the same system, such as checking objects from an untrusted plugin before adapting them to `Document` contracts.

### Knowledge self-check

1. Why does `Animal a = new Dog()` not remove methods specific to `Dog`?
2. Does `(Dog) a` change the object's runtime class?
3. What do repeated `instanceof` checks across use cases reveal about their contracts?
4. When is `Class.isInstance(...)` safe and useful?
5. Why does `(List<String>) someRawList` not prove every element is a `String`?
6. How do `getClass() == T.class` and `instanceof T` differ in the presence of subclasses?
7. When are `sealed interface` and the visitor pattern appropriate?
8. Does replacing conditionals with polymorphism automatically eliminate business errors or LSP violations?
9. Why might one `switch` at the composition root be better than an elaborate factory-class hierarchy?

**Conclusion:** Excessive casting and type checking indicate that **callers know too much about concrete classes to make business decisions**. Where behaviors share a real contract, put them in objects/strategies and use polymorphism; for uncertain data, **validate centrally at the boundary** and convert early to well-defined types. Do not ban `instanceof` or casts by slogan; use them at **the correct responsibility, layer, and scope**.
