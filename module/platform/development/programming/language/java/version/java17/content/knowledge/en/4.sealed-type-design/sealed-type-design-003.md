# Placing Behavior in Subtypes or Handling with `instanceof` in `sealed` Design (Java 17)

A `sealed` hierarchy restricts which types may directly extend or implement a parent type. Once the subtypes are known, an important design question arises: **should each subtype implement its own behavior, or should external code use `instanceof` to determine the type and handle it?**

Both options are valid in Java 17. They serve different needs: **polymorphism** distributes behavior that naturally belongs to the object; **`instanceof`** lets external code classify variants when the processing belongs to another context, such as presentation, data mapping, or external system integration.

This lesson focuses on how to choose, combine, and maintain both approaches when working with `sealed class`, `sealed interface`, and their subtypes in Java 17.

## 1. Foundation: `sealed` Restricts Object Types, Not Where Behavior Lives

Since Java 17, `sealed` is a standard language feature. For example:

```java
sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}
```

`Shape` permits only `Circle` and `Rectangle` to directly implement it. Both `record` types are implicitly `final`, so they cannot have subclasses. In this hierarchy, the concrete variants are closed to the two declared types.

A type that directly extends or implements a `sealed` type must take one of three forms:

- **`final`:** stops extending that branch; `record` is implicitly `final`.
- **`sealed`:** continues controlling which subtypes are permitted.
- **`non-sealed`:** opens the branch for other subtypes to extend or implement under normal Java rules.

For example:

```java
sealed interface Document permits PdfDocument, ExtensibleDocument {
}

final class PdfDocument implements Document {
}

non-sealed class ExtensibleDocument implements Document {
}
```

Even though `Document` has only two permitted **direct types**, you can still create subclasses of `ExtensibleDocument`. Therefore, `sealed` does not automatically guarantee that **every concrete class that may appear** belongs to a finite list if a `non-sealed` branch exists.

In a **named module**, permitted direct subtypes must be in the same module as the `sealed` type. In an **unnamed module**, they must be in the same package. The concise examples below place the types in the same file for ease of practice.

`sealed` answers the question **"which types are permitted to exist in the hierarchy?"**. It does not by itself answer **"where should behavior live?"**.

## 2. Two Approaches to Handling Variants

### Approach A: Place Behavior in Subtypes, Call via Polymorphism

The parent type declares a behavioral contract. Each subtype implements how to carry it out:

```java
sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

record Rectangle(double width, double height) implements Shape {
    @Override
    public double area() {
        return width * height;
    }
}
```

Calling code does not need to ask for the concrete type:

```java
double calculate(Shape shape) {
    return shape.area();
}
```

The JVM dispatches the `area()` call to the actual object's implementation. This is **method polymorphism** (*method overriding / dynamic dispatch*).

Key benefits:

1. **Co-locates behavior with its data and invariants:** the circle's area formula lives in `Circle`, and the rectangle's lives in `Rectangle`.
2. **Simple caller code:** many call sites can call `shape.area()` without repeating type-checking chains.
3. **Compiler support when adding variants:** if a new concrete subtype is added without implementing the required abstract method, the compiler reports an error.
4. **Encapsulation:** a subtype's implementation can use private details and change its formula without forcing callers to change.

On the flip side, if you keep adding **unrelated responsibilities** to the parent type, every subtype has to carry extra methods and inappropriate dependencies. For example, `Shape` does not necessarily need to know how to generate HTML, write JSON, or invoke a UI API.

### Approach B: Keep Subtypes as Data, Handle Externally with `instanceof`

If a function belongs to the **consumer of the object**, external code can branch by type:

```java
static String label(Shape shape) {
    if (shape instanceof Circle circle) {
        return "Circle, radius " + circle.radius();
    }
    if (shape instanceof Rectangle rectangle) {
        return "Rectangle " + rectangle.width()
                + " x " + rectangle.height();
    }
    throw new IllegalStateException("Unhandled shape type");
}
```

This is **pattern matching for `instanceof`**, a stable feature in Java 17. The expression `shape instanceof Circle circle` simultaneously:

- Checks whether the object is of type `Circle`.
- If true, binds the variable `circle` with type `Circle`; no need to write `(Circle) shape`.
- Allows accessing `circle.radius()` in branches where the compiler determines the variable is definitely assigned.

`label` may serve a particular screen, export format, or report. Keeping it outside `Shape` avoids pulling presentation concerns into the *domain contract*.

On the flip side, **type-checking `if` / `else` chains are not verified by Java 17 to be exhaustive over a `sealed` hierarchy**. When a variant is added, external handlers may still compile and hit the fallback branch at runtime. Maintainers must track those branching locations.

## 3. Complete Example: Combining Both Approaches in One Design

In real systems, a model may need **domain behavior on subtypes** and **presentation behavior externally**. The two mechanisms are not mutually exclusive.

Create the file **`ShapeDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    Circle {
        if (!Double.isFinite(radius) || radius <= 0) {
            throw new IllegalArgumentException("radius must be positive and finite");
        }
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

record Rectangle(double width, double height) implements Shape {
    Rectangle {
        if (!Double.isFinite(width) || !Double.isFinite(height)
                || width <= 0 || height <= 0) {
            throw new IllegalArgumentException("width and height must be positive and finite");
        }
    }

    @Override
    public double area() {
        return width * height;
    }
}

public class ShapeDemo {
    // Screen-specific behavior: kept outside the domain model.
    static String labelForUi(Shape shape) {
        Objects.requireNonNull(shape, "shape");

        if (shape instanceof Circle circle) {
            return "Circle, r=" + circle.radius();
        }
        if (shape instanceof Rectangle rectangle) {
            return "Rectangle, w=" + rectangle.width()
                    + ", h=" + rectangle.height();
        }

        throw new IllegalStateException(
                "Unsupported type: " + shape.getClass().getName());
    }

    public static void main(String[] args) {
        List<Shape> shapes = List.of(
                new Circle(2.0),
                new Rectangle(3.0, 4.0));

        for (Shape shape : shapes) {
            System.out.println(labelForUi(shape));
            System.out.println("Area: " + shape.area());
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 ShapeDemo.java
java ShapeDemo
```

Sample output:

```text
Circle, r=2.0
Area: 12.566370614359172
Rectangle, w=3.0, h=4.0
Area: 12.0
```

Two design decisions stand out:

**First, `area()` is domain behavior.** Circles and rectangles compute area with their own formulas. Calling `shape.area()` reflects the object's true responsibility and spares callers from knowing each type's details.

**Second, `labelForUi()` is behavior specific to a display context.** It depends on string formatting and presentation; the geometry domain has no reason to hold wording for every screen or locale.

The `record` types also validate data invariants at construction time. Regardless of where behavior lives, **data validity** belongs to the type that owns the data: you should not rely on every caller to check that a radius is positive and finite.

> The example uses `double`, which fits basic geometric calculations. If the problem involves currency or strict decimal precision, choose an appropriate representation such as `BigDecimal` instead of copying `double` arithmetic directly.

## 4. Example: Using Only `instanceof` for a Data Projection

Suppose you have payment results from a business layer. The UI needs to turn them into user-facing messages. Payment results represent **states**, whereas display wording belongs to the UI application.

Create the file **`PaymentViewDemo.java`**:

```java
import java.util.Objects;

public class PaymentViewDemo {
    sealed interface PaymentResult permits Paid, Rejected, Pending {
    }

    record Paid(String transactionId) implements PaymentResult {
    }

    record Rejected(String reasonCode) implements PaymentResult {
    }

    record Pending() implements PaymentResult {
    }

    static String toUserMessage(PaymentResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof Paid paid) {
            return "Transaction " + paid.transactionId() + " completed.";
        }
        if (result instanceof Rejected rejected) {
            return "Payment failed. Code: " + rejected.reasonCode();
        }
        if (result instanceof Pending) {
            return "Transaction is being processed.";
        }

        throw new IllegalStateException(
                "Unsupported result: " + result.getClass().getName());
    }

    public static void main(String[] args) {
        PaymentResult result = new Paid("TX-17");
        System.out.println(toUserMessage(result));
    }
}
```

Compile and run:

```bash
javac --release 17 PaymentViewDemo.java
java PaymentViewDemo
```

Output:

```text
Transaction TX-17 completed.
```

Here, `PaymentResult` does not have to declare `toUserMessage()` because presentation wording is not intrinsic to payment status. Later, you can add `toAdminMessage`, `toLogFields`, or `toCsvRow` in other components without altering the data types.

However, if an application builds many functions like `toUserMessage` with nearly identical `instanceof` chains, that is a sign to re-evaluate the design: which behaviors truly belong on the data types, which should be grouped in a dedicated handler class, or whether a centralized dispatch mechanism is needed.

In real applications, you also need **data validation** (non-blank `transactionId`, valid `reasonCode`), **message internationalization**, and avoiding direct display of sensitive internal error codes. Those details are the responsibilities of the respective model and presentation layers—not something `sealed` solves on its own.

## 5. Comparing the Two Approaches from a Design Perspective

| Question | Behavior on subtypes (polymorphism) | External handling with `instanceof` |
| --- | --- | --- |
| Who owns the implementation? | The subtype itself. | The component processing/classifying the object. |
| What does calling code see? | `shape.area()`, without knowing the concrete class. | `if (shape instanceof Circle c) ...`. |
| Adding a new **subtype**? | The compiler requires concrete subtypes to implement abstract contracts; callers usually stay unchanged. | Every branching location must be reviewed; Java 17 does not check exhaustiveness of `if` chains. |
| Adding a new **operation**? | May require adding a method to the parent type and modifying all subtypes. | Can write a new function/handler class without changing subtypes. |
| Encapsulating domain rules? | Very suitable when behavior is tightly bound to a variant's data/invariants. | Can leak domain logic across many callers if overused. |
| Depending on UI, files, frameworks, external APIs? | Risks coupling the domain model to infrastructure. | Can keep dependencies inside a dedicated component. |
| Testing | Test each variant's behavior through the common contract. | Test every branch of the handler and unsupported cases. |
| Coupling to variants | Callers have low coupling to concrete classes. | Handlers must know the names and data of concrete classes. |

There is no rule saying "always prefer polymorphism" or "with `sealed`, always use `instanceof`." What matters is identifying **who owns the behavior** and **which kind of change happens frequently**.

## 6. When Should Behavior Be Placed on Subtypes?

Prefer a method on the parent type implemented by subtypes when you see these signs.

### 6.1. Behavior Is a Natural Capability of the Variant

For example:

- `Shape.area()`: each shape knows its area formula.
- `TaxRule.calculateTax(...)`: each tax rule determines how to compute tax under its policy.
- `Expression.evaluate(...)`: each expression node knows how to evaluate based on its operands, if that responsibility is chosen for the model.
- `ValidationRule.validate(...)`: each rule checks its own condition.

Calling code usually just needs to **request the result**, without understanding each concrete class and its algorithm.

### 6.2. Adding Subtypes While Keeping Behavior Stable

If the system frequently expands its list of variants—such as adding a discount calculation, a filter, or a rule type—an interface with polymorphic methods keeps the implementation localized in the new type.

In a `sealed` hierarchy, adding a variant also requires updating the `permits` list or inheritance tree accordingly. This creates a clear structural checkpoint.

### 6.3. Multiple Places Need the Same Business Rule

If screens, batch jobs, and APIs all need to compute the same value based on object type, placing that logic in the subtypes avoids having each layer repeat an `instanceof` chain and recalculate in its own way.

### 6.4. Wanting the Compiler to Enforce Implementing the Contract

For example:

```java
sealed interface Rule permits AllowRule, DenyRule {
    boolean matches(String input);
}
```

A concrete class implementing `Rule` must provide `matches`, unless it inherits a valid implementation. This is more reliable than expecting every caller to remember checking every `Rule` kind.

Note: if you declare a `default` method in an interface or provide an implementation in a parent class, the compiler will not force every subtype to override it. Design the contract intentionally, and avoid a default implementation that merely throws `UnsupportedOperationException` and masks an unhandled variant.

## 7. When Should You Use `instanceof`?

`instanceof` is a good fit when an operation **intentionally needs to know the concrete variant** and makes more sense placed outside the model.

### 7.1. Converting to Another Representation

Tasks such as UI rendering, mapping to DTOs, formatting messages, or exporting reports may depend on the channel or audience. A domain model usually should not carry separate methods like `toHtmlForAdmin()`, `toPdfForCustomer()`, or `toKafkaPayload()` for every channel.

### 7.2. Writing an Auxiliary Feature Without Expanding the Domain Contract

For instance, a temporary debug utility classifying variants to print diagnostics, or an adapter at an integration boundary. If the scope is small and the number of types is few, a clear `instanceof` function is easier to read than extra layers of abstraction.

### 7.3. Data Types Owned by Another Module or Library

If you cannot modify the parent/subtype declarations, external handling may be appropriate. With third-party libraries, you must still respect the **public API** of the types and contract stability across library upgrades.

### 7.4. Stable Variant Set, Frequently Added Operations

Suppose a syntax tree model has fixed node types, yet you must add operations such as pretty-printing, statistics, and translating to other formats. Each operation can be organized into a dedicated component instead of continually adding methods to every node class.

When the number of operations or complexity grows substantially, you can consider **Visitor / double dispatch**. However, Visitor introduces extra interfaces and dispatch methods; for a handful of cases in Java 17, `instanceof` pattern matching is often simpler and clear enough.

## 8. The Extension Problem: Adding Variants vs. Adding Operations

Imagine a `sealed` hierarchy initially containing only `Circle` and `Rectangle`.

**Case A — adding `Triangle`:** 

- With a polymorphic design, `Triangle` must provide `area()` if required by the contract.
- Callers that only invoke `shape.area()` usually stay unchanged.
- Functions like `labelForUi` need to be reviewed to know how to display `Triangle`.

**Case B — adding drawing export to a new format:**

- If there is a separate export layer, you can add an export function in that layer.
- You do not necessarily have to edit `Circle` and `Rectangle` if format export is not a domain responsibility.
- The new exporter will need to handle the variants it supports.

Decision flow:

```text
Behavior under design
        |
        +-- Belongs to rules/invariants of the variant itself?
        |       |
        |       +-- Yes --> Consider a polymorphic method on the parent type
        |
        +-- Depends on external context (UI, DTO, integration...)?
                |
                +-- Yes --> Consider an external handler using instanceof

Then ask further:
  - Which places will need this same behavior?
  - Does the project add variants or operations more often?
  - How stable must the contract between modules be?
  - Which branches must be updated when the model changes?
```

A well-structured system divides **different behaviors** according to their responsibilities rather than forcing everything into a single technique.

## 9. Java 17-Specific Considerations

### 9.1. `instanceof` Pattern Matching Is Stable

You can write:

```java
if (shape instanceof Circle circle) {
    System.out.println(circle.radius());
}
```

No manual cast is needed:

```java
if (shape instanceof Circle) {
    Circle circle = (Circle) shape;
    System.out.println(circle.radius());
}
```

The second snippet is still valid Java, but it is longer and invites duplicating the target type expression. In new Java 17 code, the first form is generally more readable.

Pattern variables are only in scope where the compiler determines the type test succeeded (*flow scoping*). For example:

```java
if (!(shape instanceof Circle circle)) {
    return;
}

// After the return branch, the compiler knows shape is a Circle in the remaining flow.
System.out.println(circle.radius());
```

The snippet above uses this form **inside a `void` method**; if the method must return a value, adjust the `return` statement accordingly.

### 9.2. `null` and Unsupported-Variant Handling

`instanceof` evaluates to `false` when the object reference is `null`. Thus:

```java
if (shape instanceof Circle circle) {
    // Only enters here when shape is actually a Circle.
}
```

If the function does not accept `null`, check explicitly at the top of the method:

```java
Objects.requireNonNull(shape, "shape");
```

After the branches, you can throw `IllegalStateException` when encountering an unsupported variant so missed updates are caught early. Avoid returning a "plausible-looking" value that hides an unhandled new type.

### 9.3. `sealed` Does Not Make `if` Chains Exhaustive at Compile Time

Java 17 **does not automatically enforce** that a chain like:

```java
if (value instanceof A a) {
    // ...
} else if (value instanceof B b) {
    // ...
}
```

covers every type declared in `permits`. Therefore, when modifying the hierarchy, update external handlers and test the relevant variants.

Do not confuse this with **pattern matching for `switch`**: in Java 17, that feature is still in **preview** (JEP 406) and requires preview mode; syntax like `switch (shape) { case Circle c -> ... }` is not standard syntax enabled by default in Java 17. To keep Java 17 practice exercises on stable features, the examples here use `if` with `instanceof`.

In addition, **record patterns** with destructuring syntax such as `instanceof Circle(double radius)` are not part of stable Java 17; access `record` components via accessors like `circle.radius()`.

### 9.4. `non-sealed` Expands the Actual Runtime Set of Cases

If a branch is `non-sealed`, you cannot assume the few concrete types you knew when writing code are all the types that can occur. An `instanceof` function listing a few concrete classes may miss new subclasses of that open branch.

In an open branch, a fallback strategy, a polymorphic contract on the base type, or a clear extension interface becomes even more important.

### 9.5. Place Rules in the Right Layer When External Services Are Needed

Not every business behavior has to be a method on a `record` or entity. If a rule needs database access, HTTP calls, event publishing, or multiple repositories, an **application/domain service** with dependency injection is usually much better than stuffing dependencies into subtypes just to "have polymorphism."

When processing inside a service, you can still use:

- **Polymorphism** to obtain intrinsic information or behavior of a variant.
- **`instanceof`** to branch when integrating per case.
- **Strategy/registry** if replaceable or configuration-registered handlers are needed.

Choosing between polymorphism and `instanceof` depends on design responsibility, not merely on whether a behavior is labeled "business" or "technical."

## 10. Common Design Mistakes

### Mistake 1: Repeating an `instanceof` Chain for the Same Domain Rule

An example not to replicate:

```java
double calculateArea(Shape shape) {
    if (shape instanceof Circle c) {
        return Math.PI * c.radius() * c.radius();
    }
    if (shape instanceof Rectangle r) {
        return r.width() * r.height();
    }
    throw new IllegalStateException("Unknown shape");
}
```

If this is a domain rule needed in many places, replace it with `shape.area()`. When every caller calculates it independently, it becomes easy to forget a variant, miscalculate a formula, or apply rules inconsistently.

### Mistake 2: Forcing All Presentations into Subtypes

For example, an interface `PaymentResult` with `renderHtml()`, `renderMobileScreen()`, `toCsv()`, `createEmailBody()`, etc., couples the model to external formats and technologies.

If these operations are owned by other layers and evolve independently of payment state, consider separate converters or formatters.

### Mistake 3: Treating `sealed` as an Automatic Handler for All Variants

`sealed` only **controls the set of direct subtypes** at the language level. It does not implement logic, dispatch across subtypes, or turn a missing `if` branch into a compile error.

### Mistake 4: Adding a `default` Method Just to Avoid Updating Subclasses

```java
sealed interface Action permits SaveAction, DeleteAction {
    default void execute() {
        throw new UnsupportedOperationException("Not implemented");
    }
}
```

This design can push missing-implementation bugs to runtime. If every variant must support `execute`, consider declaring an abstract method:

```java
sealed interface Action permits SaveAction, DeleteAction {
    void execute();
}
```

Then concrete subtypes must implement the contract unless they already inherit a valid implementation from a parent branch.

### Mistake 5: Mixing State-Based Conditions and Type-Based Classification Arbitrarily

`instanceof` asks **which type** an object belongs to, not "what is its current business state?". For instance, an `Order` can transition from processing to completed without changing into a different class. Do not create endless subtypes just to replace every `if (status == ...)` check with type checks.

Choose `sealed` when variants genuinely have different identities and contracts; choose a state attribute when it is mutable data of the same entity.

## 11. Practice Exercises

### Exercise 1: Designing a Discount Rule Hierarchy

You have `DiscountRule` with two types: `FixedDiscount` and `PercentageDiscount`. Both the sales system and a batch job need to compute the discounted amount using the same rule.

**Suitable design direction:** declare a method such as `applyTo(BigDecimal originalPrice)` on `DiscountRule`; each type implements its own calculation. Put parameter checks such as "non-negative amount" or "valid percentage" into the class/record owning the data. Do not let each caller branch with `instanceof` to recompute the formula.

### Exercise 2: Exporting Order Status Across Channels

You have outcome states `Accepted`, `Rejected`, and `Pending`, and need to produce messages for a web UI, operational logs, and a CSV file. Representations vary by channel.

**Suitable design direction:** keep status data in the `sealed` variants and build formatters/mappers in the layers responsible for each channel. `instanceof` can be used to read each variant's data inside a small, clear handler. If the number of handlers grows and branches repeat heavily, re-evaluate the architecture or consider Visitor.

### Exercise 3: Adding a New Variant

Suppose you add `Triangle` to the `Shape` example.

1. `Shape`'s `permits` must be updated.
2. `Triangle` must implement `area()` if it is a concrete type and does not inherit an implementation.
3. `ShapeDemo.labelForUi` needs to know how to display `Triangle`.
4. Callers that only invoke `shape.area()` do not need to change to add a new type-checking branch.

This is the clearest difference between **extending a subtype hierarchy** and **extending external operations**.

## 12. Design Takeaways

- **Use polymorphism** when a behavior is natural, consistent, and meaningful for every variant of the parent type.
- **Use `instanceof` pattern matching** when an external function needs to distinguish concrete types for conversion, presentation, or integration.
- **Combine both approaches** when an object has domain behavior and is also consumed by multiple external components.
- **Do not rely on `sealed` to assume an `if` chain covers every type.** Review all handlers when the variant list changes, especially if a `non-sealed` branch exists.
- **In Java 17**, `sealed` and pattern matching for `instanceof` are both stable; avoid depending on preview pattern matching for `switch` when preview mode is not intended.

## Official References

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): subclass restriction model, `permits`, `sealed`, and `non-sealed` in Java 17.
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): type-testing syntax with pattern variables and variable scoping rules.
- [JEP 395 — Records](https://openjdk.org/jeps/395): `record` data types, `final` behavior, and accessors.
- [Java Language Specification, Java SE 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): class declarations, methods, and `sealed` hierarchies.
- [Java Language Specification, Java SE 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): `sealed interface` and implementation rules.
- [JEP 406 — Pattern Matching for `switch` (Preview)](https://openjdk.org/jeps/406): distinguishing experimental syntax in Java 17 from stabilized language syntax.
