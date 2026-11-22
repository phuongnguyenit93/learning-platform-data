# Avoid Constant Interfaces and Inheritance Hierarchies Solely for Code Reuse

In Java, interfaces and abstract classes are tools for modeling contracts, shared behavior, and type relationships. However, using an interface solely to group constants or creating an inheritance hierarchy just to reuse a few lines of code often makes a design harder to understand, harder to change, and prone to unintended dependencies.

Two principles to keep in mind:

- **Do not use constant interfaces:** do not force a class to use `implements` on an interface just to reference the constants declared in that interface.
- **Favor composition over inheritance when the goal is solely code reuse:** use inheritance when the subtype can truly substitute for the supertype and uphold the supertype's contract.

This does not mean avoiding every interface or all inheritance. An interface describes behavior that multiple types can provide; an abstract class can hold shared state and shared implementation when an appropriate abstraction relationship exists. The problem lies in choosing a construct merely for convenience in accessing constants or reusing code, rather than accurately reflecting the model's meaning.

## 1. What Is a Constant Interface?

In Java, fields declared in an interface are implicitly `public static final`. Therefore, an interface can be written to hold constants:

~~~java
public interface HttpConstants {
    int DEFAULT_TIMEOUT_SECONDS = 30;
    int MAX_RETRIES = 3;
}
~~~

This becomes the **constant interface anti-pattern** when a class implements the interface merely to use the constant names directly:

~~~java
// Do not design it this way.
class HttpClient implements HttpConstants {
    void connect() {
        int timeout = DEFAULT_TIMEOUT_SECONDS;
        // ...
    }
}
~~~

`HttpClient` is not a kind of `HttpConstants`. It only needs to use a few configuration values, yet `implements` makes the constants part of the type's API and creates the impression that the class has a type relationship with the interface.

The main problems:

- **Misrepresents the type relationship:** `implements` should indicate that a class provides behavior according to the interface's contract.
- **Leaks implementation details:** constants may appear in the implementing class's public API, even though users of the class do not need to know where they come from.
- **Increases unnecessary coupling:** the class becomes tied to the interface solely for shared values, so renaming or reorganizing constants can affect many places.
- **Makes design changes harder:** an interface should be designed around behavior and contracts; a group of constants usually does not provide a useful behavioral contract.

In particular, having a class implement an interface to access constants yields no polymorphism benefit. No behavior is substituted through the interface; the only goal is to shorten how the constant names are written.

## 2. Better Ways to Organize Constants

Choose where to place a constant based on the meaning of the data, its scope of use, and its ownership.

### Approach A: Place Constants in the Related Class

If a value is meaningful only to a single class, place it directly in that class:

~~~java
public final class HttpClient {
    private static final int DEFAULT_TIMEOUT_SECONDS = 30;
    private static final int MAX_RETRIES = 3;

    public void connect() {
        int timeout = DEFAULT_TIMEOUT_SECONDS;
        // Use timeout when connecting.
    }
}
~~~

`private` constants do not become part of the public API. Maintainers can also easily identify which class the values belong to.

### Approach B: Use a Non-Instantiable Utility Class

When multiple classes genuinely need to share a group of constants belonging to the same domain, you can use a `final` class with a private constructor:

~~~java
public final class HttpDefaults {
    private HttpDefaults() {
        // Disallow instantiation of the constants class.
    }

    public static final int DEFAULT_TIMEOUT_SECONDS = 30;
    public static final int MAX_RETRIES = 3;
}
~~~

A class uses the value via its qualified name:

~~~java
int timeout = HttpDefaults.DEFAULT_TIMEOUT_SECONDS;
~~~

The name `HttpDefaults` indicates that the values belong to the HTTP configuration group; it does not pretend that the class using the constants is a subtype of some contract.

Do not turn a constants class into a dumping ground for every value in the entire application. If constants belong to different domains, place them near the type or configuration that owns them. If a value varies by environment or needs to be tested, passing configuration into the object is usually better than reading a global constant.

### Approach C: Use an Enum for a Finite Set of Choices

If the data represents a predefined set of meaningful values, consider an `enum` instead of discrete integers or strings:

~~~java
enum RetryMode {
    NONE,
    FIXED_DELAY,
    EXPONENTIAL_BACKOFF
}
~~~

An `enum` lets you strongly type the choices and write clear `switch` statements. However, an enum is not a replacement for every constant; a numeric value such as a timeout can still be appropriate as a `static final` field or a typed configuration.

### Approach D: Static Import When It Improves Readability

Java supports static imports:

~~~java
import static java.lang.Math.PI;
~~~

You can then use `PI` instead of `Math.PI`. Static imports are useful when the source is already clear and repeating the class name adds noise. For application constants, use them sparingly: if the standalone name does not indicate where the value comes from, writing `HttpDefaults.DEFAULT_TIMEOUT_SECONDS` is usually easier to understand.

A static import only changes how names are written in source code; it does not fix a constant interface design if a class still implements the interface just to access constants.

## 3. When Is an Interface Truly Appropriate?

An interface should describe a behavioral contract or a capability that different types can provide. For example, a program may need multiple discount policies, all of which must answer the question: "For this amount, how much is the discount?"

~~~java
import java.math.BigDecimal;

interface DiscountPolicy {
    BigDecimal discountFor(BigDecimal subtotal);
}
~~~

This interface has a single abstract method, so it can be implemented by different classes or expressed as a lambda when the target type is known. It has a clear purpose: the caller depends on the discount-calculation contract without having to know the specific calculation logic.

By contrast, an interface containing only `int TIMEOUT = 30;` does not define any behavior that an implementing class must provide. Do not add `implements` just to avoid writing the class name before a constant.

An interface can still declare constant fields when those constants are an intentional part of the contract and are meaningful to consumers of the interface. The rule to avoid is using an interface as a convenient namespace for values unrelated to a behavioral contract.

## 4. Why Should You Not Create an Inheritance Hierarchy Solely for Code Reuse?

Suppose two classes need the same piece of processing logic. You could create a superclass to hold that code and have both classes inherit from it. This approach may seem to save code, but inheritance also creates a type relationship: the subclass is treated as a kind of the superclass and must uphold the superclass's contract.

If two classes merely happen to share a few execution steps without having an "is-a" relationship, putting them into the same inheritance hierarchy can produce a flawed model.

Common risks:

- **Invalid type relationship:** the subclass may fail to meet the expectations of users of the superclass.
- **Coupling to implementation details:** the subclass may rely on `protected` fields, method call ordering, or the internal state of the superclass.
- **Superclass changes break subclasses:** a seemingly harmless change in the superclass can alter the behavior of a subclass.
- **Hard to combine multiple capabilities:** Java allows a class to directly extend only one other class, so using inheritance hierarchies to combine independent features quickly becomes limiting.
- **Harder to test:** a subclass often needs to initialize and conform to the superclass's state, even when the reused part is only a small operation.

Inheritance is appropriate when there is a genuine "is-a" relationship, the subclass can substitute for the superclass wherever the superclass is required, and the contract still holds. Code reuse is a potential benefit of inheritance, but by itself it is not enough to justify an inheritance relationship.

## 5. Favor Composition and Delegation

**Composition** means an object holds or receives another object in order to use its functionality. **Delegation** is when an object forwards part of its work to that component object.

For example, instead of having `CheckoutService` extend a discount class just to obtain the calculation method, let the service receive a `DiscountPolicy`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

interface DiscountPolicy {
    BigDecimal discountFor(BigDecimal subtotal);
}

final class NoDiscountPolicy implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return BigDecimal.ZERO.setScale(2);
    }
}

final class TenPercentDiscount implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);
    }
}

final class CheckoutService {
    private final DiscountPolicy discountPolicy;

    CheckoutService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }

    BigDecimal totalFor(BigDecimal subtotal) {
        BigDecimal discount = discountPolicy.discountFor(subtotal);
        return subtotal.subtract(discount);
    }
}

public class CompositionDemo {
    public static void main(String[] args) {
        BigDecimal subtotal = new BigDecimal("100.00");
        CheckoutService checkout =
                new CheckoutService(new TenPercentDiscount());

        BigDecimal total = checkout.totalFor(subtotal);
        System.out.println("Subtotal: " + subtotal);
        System.out.println("Discount: "
                + subtotal.subtract(total).setScale(2));
        System.out.println("Total: " + total);
    }
}
~~~

Save the code in a file named **CompositionDemo.java**, then compile and run it with Java 17 or later:

~~~bash
javac CompositionDemo.java
java CompositionDemo
~~~

Stdout output:

~~~text
Subtotal: 100.00
Discount: 10.00
Total: 90.00
~~~

In this example, `CheckoutService` is not a kind of `TenPercentDiscount`; the service **has a** discount policy. It only calls the method through the `DiscountPolicy` interface. You can swap the discount policy without creating a new subclass of `CheckoutService`.

Accepting the policy through the constructor from outside also makes testing easier: you can pass `NoDiscountPolicy` or a test policy to verify the result. In a real application, you should validate input values according to domain requirements, such as handling `null` and disallowing negative subtotals if business rules do not accept them.

## 6. Signs That an Inheritance Hierarchy Was Created Solely for Code Reuse

When reviewing a `Base*` class with multiple subclasses, do not just count the number of shared lines. Check these questions tied directly to the anti-pattern:

1. **Is there a genuine substitutability contract?** If a client accepts the superclass type, do all subclasses preserve the same meaning for their public methods? If not, the inheritance relationship may be wrong even though code is reused.
2. **Is the reused part just a utility?** If the superclass only contains a few formatting, calculation, or connection functions not tied to a type family, consider an appropriately scoped helper or a collaborator object.
3. **Do subclasses depend on internal details?** Having to access numerous `protected` fields, call `super` in an implicit order, or override methods to disable logic is a sign of a fragile design.
4. **Do capabilities change independently?** If adding a processing method forces creating many subclasses for every combination, composition with role-focused interfaces can make the boundaries of change clearer.

Composition also has a cost: adding dependencies, constructors, and sometimes forwarding classes. Choose it when the component has its own distinct responsibility; if there is only a small pure function, a simple helper may suffice. With a genuine "is-a" relationship and a stable shared workflow, inheritance remains a reasonable choice.

## 7. The Liskov Substitution Principle and the Superclass Contract

The Liskov Substitution Principle (LSP) states that objects of a subtype must be usable wherever the supertype is expected without breaking the caller's valid expectations.

For example, if a superclass specifies that the `save()` method always persists data successfully or throws a documented exception, a subclass should not silently skip the save operation just to reuse another utility method. Inheritance entails the responsibility of upholding the superclass's contract, including input preconditions, results, invariants, and observable behavior.

If two classes only need to share a formatting function or an algorithm, that part can be moved into an appropriately scoped helper or a separate service object. This avoids forcing one class to become a subclass of the other when they do not have a valid substitutability relationship.

## 8. Abstract Classes Remain Useful When Shared Implementation Is Appropriate

"Favor composition" should not be interpreted as forbidding abstract classes. Abstract classes are useful when subclasses truly belong to the same conceptual family and share state or part of an algorithm under a clear contract.

For example, an abstract class `FileProcessor` can define a common `process()` workflow and require subclasses to provide the `read()` or `transform()` steps. This is a template method design: the superclass controls the overall workflow, while subclasses customize the steps designed for extension.

Conversely, if a class only extends `BaseUtilities` to obtain a `formatDate()` method when it is not a kind of `BaseUtilities`, consider placing the formatting operation in a separate class or service and calling it. Do not create catch-all superclasses like `BaseEverything` just to bundle unrelated functions.

## 9. How to Choose a Solution by Situation

- **A constant used in only one class:** place it in that class, usually as `private static final`.
- **A group of constants sharing a domain:** consider a `final` class with a private constructor, or an appropriate configuration type.
- **A meaningful finite set of choices:** consider an `enum`.
- **Multiple classes needing the same behavioral contract:** define an interface describing that behavior.
- **Classes in the same family with a substitutability relationship and clear shared implementation:** consider an abstract class or a concrete superclass.
- **A class that simply needs to invoke a capability of another component:** use composition/delegation.
- **A small, pure, stateless algorithm:** consider an appropriately scoped helper method; there is no need to build an inheritance hierarchy just to share it.

Before adding an interface or a superclass, ask yourself: "Is this type relationship valid from a domain perspective? Can consumers rely on this contract? If code reuse were not needed, would I still want this relationship to exist?" If the answer to the last question is no, composition or a helper is usually worth considering instead.

## 10. Common Design Mistakes

- **`implements` solely to access constants:** move the constants to the owning class or to a clearly named configuration class.
- **An interface containing only data fields whose name implies a contract:** design the interface around the behavior actually needed; keep constants separate if they are not part of the contract.
- **A catch-all "utility" superclass:** split independent responsibilities into small components with names that accurately describe their roles.
- **Inheriting to avoid a few lines of duplication:** evaluate whether the duplication genuinely needs to be eliminated; if so, extract a method or use a component with a clear responsibility.
- **A subclass overriding to disable superclass behavior:** this can be a sign that the subclass does not uphold the contract or that the superclass has poorly drawn responsibility boundaries.
- **Using `protected` to expose state solely so subclasses can reuse it:** consider encapsulating the state and providing a small method or interface instead of letting subclasses depend on internal details.
- **Composition creating too many forwarding classes:** extract a component only when it has its own responsibility or point of change; keep the code simple when a small helper suffices.

## 11. Design Review Process

1. Identify why the class is implementing an interface or extending a superclass: a type contract, behavior reuse, or merely accessing constants.
2. For a constant interface, move the values to the owning class, a configuration class, or an appropriate domain type; update references to be explicit and remove the meaningless `implements`.
3. For an inheritance hierarchy used for reuse, verify the "is-a" relationship, the substitutability contract, and the subclass's dependence on the superclass's state or details.
4. If only a single capability is needed, extract a small behavioral interface or a concrete component and have the class invoke it via composition/delegation.
5. Write or run tests for the behavior before and after the change, paying attention to observable results and edge cases.
6. Name interfaces, abstract classes, components, and constants after their actual roles; avoid generic names that obscure responsibilities.

Good Java design uses interfaces to describe behavior, abstract classes to share implementations within a meaningful type family, and composition to coordinate independent capabilities. Avoiding constant interfaces and inheritance hierarchies created solely for code reuse makes relationships between classes clearer, reduces unintended coupling, and makes changes, testing, and maintenance easier.
