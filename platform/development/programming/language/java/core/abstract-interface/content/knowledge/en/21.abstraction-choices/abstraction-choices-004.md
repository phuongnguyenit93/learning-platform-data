# Combining a Public Interface with an Optional Support Abstract Class

When designing a Java API, it is often good practice to publish an **interface that describes the contract** and also provide an **abstract class as an optional support class**. API users can implement the interface directly if they want to control the entire behavior themselves, or extend the abstract class to reuse the shared implementation.

This design separates two decisions: *what an object must be able to do* and *how an implementation can reuse that behavior*. Code calling the API only needs to depend on the interface; the abstract class serves as a convenient option, not a mandatory requirement.

## 1. The Public Interface Defines the Contract

The interface should describe the operations that API users are allowed to call and the conditions that are meaningful for those operations. The contract should focus on observable behavior: inputs, results, possible errors, and the guarantees that every implementation must satisfy.

For example, a text renderer can be described by an interface:

```java
interface TextRenderer {
    String render(String text);
}
```

Code that uses the renderer only needs to know the `TextRenderer` type and call `render`. It does not need to know whether the object is a class written directly from the interface or a class extending the abstract class.

```java
static void show(TextRenderer renderer, String value) {
    System.out.println(renderer.render(value));
}
```

This is the key point of a public contract: callers rely on the capabilities promised by the interface, rather than depending on a concrete implementation class.

## 2. The Abstract Class Provides Shared Implementation

The interface above only defines the `render` operation. An abstract class can provide a common algorithm and let subclasses customize a small step via a hook method declared as `protected`.

This pattern is often called a **skeletal implementation** when the abstract class reduces the amount of code an implementer has to write. When the base class controls the order in which steps execute, it is also a form of **Template Method**.

```java
import java.util.Objects;

abstract class AbstractTextRenderer implements TextRenderer {
    @Override
    public final String render(String text) {
        Objects.requireNonNull(text, "text");
        return "[" + renderContent(text.trim()) + "]";
    }

    protected abstract String renderContent(String normalizedText);
}
```

The base class performs the common steps: rejecting `null` input, trimming leading and trailing whitespace, and wrapping the result in square brackets. The `renderContent` method is the customization point for subclasses.

The `final` keyword on `render` ensures that subclasses do not alter the order of the common algorithm. This is an intentional design decision: it is appropriate when the process needs to be kept stable, but unsuitable if each subclass needs to define the entire `render` process on its own.

## 3. Both Implementation Approaches Are Valid

A class using the interface can implement the contract on its own without extending the abstract class:

```java
import java.util.Objects;

class DirectRenderer implements TextRenderer {
    @Override
    public String render(String text) {
        Objects.requireNonNull(text, "text");
        return text.trim();
    }
}
```

Or it can extend the support class and provide only the missing step:

```java
import java.util.Locale;

class UppercaseBracketRenderer extends AbstractTextRenderer {
    @Override
    protected String renderContent(String normalizedText) {
        return normalizedText.toUpperCase(Locale.ROOT);
    }
}
```

Both objects are instances of `TextRenderer`. The calling class does not need to check the concrete class type or have two different handling branches.

## 4. Complete Runnable Example

Save all of the following code in a file named `InterfaceAndAbstractSupportDemo.java`. The interface and support classes do not have the `public` keyword, so they can live in the same file as the public class:

```java
import java.util.Locale;
import java.util.Objects;

interface TextRenderer {
    String render(String text);
}

abstract class AbstractTextRenderer implements TextRenderer {
    @Override
    public final String render(String text) {
        Objects.requireNonNull(text, "text");
        return "[" + renderContent(text.trim()) + "]";
    }

    protected abstract String renderContent(String normalizedText);
}

class DirectRenderer implements TextRenderer {
    @Override
    public String render(String text) {
        Objects.requireNonNull(text, "text");
        return text.trim();
    }
}

class UppercaseBracketRenderer extends AbstractTextRenderer {
    @Override
    protected String renderContent(String normalizedText) {
        return normalizedText.toUpperCase(Locale.ROOT);
    }
}

public class InterfaceAndAbstractSupportDemo {
    private static void show(TextRenderer renderer, String value) {
        System.out.println(renderer.render(value));
    }

    public static void main(String[] args) {
        TextRenderer direct = new DirectRenderer();
        TextRenderer supported = new UppercaseBracketRenderer();

        show(direct, " Java ");
        show(supported, " Java ");
    }
}
```

Compile and run using JDK 17 or later:

```text
javac -encoding UTF-8 InterfaceAndAbstractSupportDemo.java
java InterfaceAndAbstractSupportDemo
```

Expected output:

```text
Java
[JAVA]
```

The first line shows that the direct implementation can choose its own handling. The second line shows that the subclass reuses the common process of the abstract class and only supplies the content formatting.

In real-world design, the types and methods of a public API are usually placed in separate files. The example above groups them into a single file so learners can compile and run it immediately without project configuration.

## 5. Why Should the Abstract Class Be Optional?

Java allows a class to directly extend only one other class. If an API forces every implementation to extend an abstract class, users may no longer be able to extend another class that fits their design.

When the interface is the primary contract, users can choose:

- **Direct implementation:** suitable when the behavior differs, another class needs to be extended, or the support implementation does not fit.
- **Extending the abstract class:** suitable when you want to reuse the provided algorithm, state, constructors, or helper methods.
- **Combining with a separate base class:** if they can extend another class, users can still implement the public interface and organize their shared code themselves.

By keeping the abstract class optional, the API can provide convenience without taking away the user's choice of class structure.

## 6. How Is an Interface with a `default` Method Different?

A Java interface can provide a `default` method to share simple behavior directly within the contract. This approach is useful when the behavior does not require object state or a complex hook system.

Example:

```java
interface Named {
    String name();

    default boolean hasName() {
        return name() != null && !name().isBlank();
    }
}
```

Every `Named` implementation receives `hasName` if it does not override that method. However, a `default` method does not replace every role of an abstract class. An abstract class can have constructors, instance fields, `protected` methods, and a reusable sequence of implementation steps.

A practical guideline:

- Use an interface to publish the contract and small `default` methods when the shared behavior genuinely fits every implementation.
- Use an abstract class when you need a base implementation with state, constructors, helper methods, or a Template Method.
- Keep the abstract class optional if users do not need to extend it in order to fulfill the contract.

You should not add an abstract class just to wrap an interface without providing actual shared value.

## 7. Keeping the Public Contract Stable

The public interface is the dependency point for client code. Adding a new abstract method can break compilation for existing implementation classes until they implement that method.

A support abstract class can reduce the effort for subclasses extending it if the base class provides an appropriate implementation for the new method. However, classes implementing the interface directly must still conform to the new contract. Therefore, an abstract class cannot be treated as a way to automatically guarantee backward compatibility for all clients.

When evolving an already widely used API:

1. Only add a public operation when it truly belongs in the interface's contract.
2. Consider whether a `default` method can provide compatible behavior.
3. If direct implementations need to be supported, clearly define how the new behavior works with existing implementations.
4. If a support abstract class exists, update it consistently while still treating direct implementations as part of the API.
5. Test both classes extending the abstract class and classes implementing the interface directly.

A `default` method also needs careful design: adding a method whose signature matches or conflicts with another interface can cause conflicts when combining multiple interfaces. You should not add a default method merely to avoid thinking through the contract.

## 8. Common Design Mistakes

- **Forcing all users to extend the abstract class:** this limits Java's single inheritance and turns the support class into an unnecessary constraint.
- **Letting calling code depend on the support class:** whenever possible, accept parameters using the public interface so that both direct implementations and abstract-class-based implementations can be used.
- **Putting all behavior into the interface even when state or hooks are needed:** consider an abstract class if the shared algorithm requires instance fields, constructors, or controlled customization steps.
- **Using an abstract class without meaningful reuse:** if the class only repeats the interface signatures, it can complicate the API without helping users.
- **Assuming an abstract class automatically guarantees backward compatibility:** changes to the interface contract still affect direct implementations.
- **Allowing subclasses to override a step that must stay unchanged:** if the algorithm needs to preserve ordering, consider a `final` coordinating method and clear `protected` hooks; only use this approach when restricting overrides is a genuine requirement.

## 9. Selection Process

First, identify the operations that every object needs to provide and publish them via an interface. Next, identify what parts of the algorithm or state can be shared. If the shared part is simple and does not require state, a `default` method may be sufficient. If constructors, state, hooks, or a skeletal algorithm are needed, provide an abstract class that implements that interface.

Finally, ensure that client code can work through the interface without having to know whether the support class is used. Test both implementation paths to verify that they satisfy the same contract.

Combining a public interface with an optional abstract class allows an API to both maintain a clear contract and provide useful shared code. The interface defines how users interact; the abstract class reduces implementation effort when appropriate, while leaving other users free to choose how to implement the contract.
