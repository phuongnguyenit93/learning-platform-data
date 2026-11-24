# Constructor Restrictions in SimpleEvaluationContext

## 1. Why Does SimpleEvaluationContext Restrict Constructors?

Spring Expression Language (SpEL) can create new objects using constructor references, for example:

```text
new java.lang.String('hello')
new com.example.Address('Ho Chi Minh City')
```

This capability is useful when an expression needs to create a value or object during evaluation. However, constructor invocation also allows expressions to instantiate object types that the application does not want to expose to expression authors.

`SimpleEvaluationContext` is designed for scenarios requiring a restricted subset of SpEL, typically data binding and property-based filtering. Therefore, it intentionally excludes three feature groups:

- Java type references via `T(...)`.
- Constructor references via `new Type(...)`.
- Bean references via `@beanName` syntax.

This is part of the context's design, not a configuration error. The `SimpleEvaluationContext` builder has no option to enable constructor invocation or register a `ConstructorResolver`.

## 2. How Do Constructor References Work in SpEL?

Object creation syntax:

```text
new FullyQualifiedTypeName(argument1, argument2, ...)
```

Example with a standard Java type:

```java
ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression(
        "new java.lang.String('hello')")
        .getValue(String.class);
```

Example with an application class:

```text
new com.example.Address('Ho Chi Minh City', 'VN')
```

SpEL must identify the type to instantiate and find a constructor matching the number and types of arguments. Constructor lookup is performed through the `ConstructorResolver` instances provided by the EvaluationContext.

In `StandardEvaluationContext`, SpEL provides a default reflection-based resolver to search for constructors. In `SimpleEvaluationContext`, the constructor resolver list is always empty, so expressions cannot resolve constructors.

## 3. SimpleEvaluationContext Does Not Allow Creating Objects with new

The following example can be parsed syntactically, yet cannot execute successfully with SimpleEvaluationContext:

```java
ExpressionParser parser = new SpelExpressionParser();

var simpleContext =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

var expression = parser.parseExpression(
        "new java.lang.String('hello')");

// Not supported in SimpleEvaluationContext:
String value = expression.getValue(simpleContext, String.class);
```

During evaluation, SpEL finds no constructor resolver to handle `new`. Calling `getValue()` therefore fails with a SpEL evaluation error. Do not rely on a specific error message across versions; the stable guarantee is that constructor invocation is outside this context's feature set.

Constructors of application classes are restricted in the same way:

```text
new com.example.Address('District 1')
```

There is no `withConstructors()` or `withConstructorResolvers()` call on the builder to turn this feature on. If an expression needs to create objects with `new`, reconsider the context design or move object creation into Java.

## 4. How to Check This Restriction via the API

`SimpleEvaluationContext` implements `EvaluationContext`. Calling `getConstructorResolvers()` on this context returns an empty list:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

boolean hasConstructorResolvers =
        !context.getConstructorResolvers().isEmpty();

// false
```

The empty list is technical proof that the context provides no constructor resolution mechanism. The builder has no method to replace this list.

SimpleEvaluationContext also does not support type references. Its TypeLocator is configured to throw an error when an expression attempts to resolve `T(...)`. Thus, both of the following expressions fall outside the supported scope:

```text
new java.lang.String('hello')
T(java.lang.String)
```

Constructor references and type references are related yet separate syntaxes: `new` requests creating an instance, while `T(...)` references a Class object. SimpleEvaluationContext excludes both.

## 5. Capabilities the Builder Still Supports

Restricting constructors does not mean SimpleEvaluationContext cannot be customized. The builder allows selecting the capabilities needed for data binding:

| Context Creation Method | Primary Capability |
|---|---|
| `forReadOnlyDataBinding()` | Reads public properties via DataBindingPropertyAccessor. |
| `forReadWriteDataBinding()` | Reads and writes public properties. |
| `forPropertyAccessors(...)` | Uses custom PropertyAccessors, typically for custom data structures. |
| `withInstanceMethods()` | Enables a DataBindingMethodResolver to invoke instance methods within data binding scope. |
| `withMethodResolvers(...)` | Registers controlled MethodResolvers. |
| `withTypeConverter(...)` or `withConversionService(...)` | Configures type conversion. |
| `withRootObject(...)` | Selects the default root object. |
| `withAssignmentDisabled()` | Disables assignment in expressions. |

None of the methods in the table enable constructor invocation. In particular, `withInstanceMethods()` only allows calling instance methods via DataBindingMethodResolver; it does not open constructors, static methods, type references, or bean references.

Example creating a read-only property context:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withRootObject(customer)
                .build();

String name = parser.parseExpression("name")
        .getValue(context, String.class);
```

Example allowing instance methods in data binding:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .withRootObject(customer)
                .build();

String displayName = parser.parseExpression(
        "displayName('Customer:')")
        .getValue(context, String.class);
```

Enabling instance methods does not alter the constructor resolver list; `new Type(...)` remains unsupported.

## 6. Alternative 1: Create the Object in Java and Pass It into Context

If the needed object is known ahead of time, the simplest approach is instantiating it in Java before evaluating the expression. Then pass the object as the root or register it as a variable.

Example passing the object as root:

```java
Address address = new Address("Ho Chi Minh City", "VN");

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withRootObject(address)
                .build();

String city = parser.parseExpression("city")
        .getValue(context, String.class);
```

Example passing the object via a variable:

```java
Address address = new Address("Ho Chi Minh City", "VN");

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("address", address);

String city = parser.parseExpression("#address.city")
        .getValue(context, String.class);
```

This keeps object creation responsibility in Java, where the application controls the constructor and arguments. The expression merely reads or processes the supplied object.

## 7. Alternative 2: Use an Explicitly Permitted Factory Method

If an expression needs to request creating a value from certain parameters, you can supply a narrowly scoped factory method instead of allowing arbitrary constructor calls.

SimpleEvaluationContext supports functions registered as variables. A function can be a static Java Method or MethodHandle. Example:

```java
public final class AddressFunctions {

    private AddressFunctions() {
    }

    public static Address createAddress(String city) {
        return new Address(city, "VN");
    }
}
```

Register the factory method:

```java
Method factory = AddressFunctions.class.getMethod(
        "createAddress", String.class);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("createAddress", factory);

Address address = parser.parseExpression(
        "#createAddress('Ho Chi Minh City')")
        .getValue(context, Address.class);
```

This does not enable constructor invocation. The expression can only call the specific function registered by the application. Keep the factory focused on one clear task, validate arguments, and avoid returning objects with many sensitive methods.

Functions and variables share a namespace in SimpleEvaluationContext. Therefore, do not register a function and a variable with the same name.

If dynamic object creation is unnecessary, passing a pre-created object as the root or a variable remains simpler and easier to control.

## 8. When Is StandardEvaluationContext Needed?

If the business requirement genuinely requires expressions to call constructors themselves, full SpEL provides `StandardEvaluationContext`. This context has a default reflection-based constructor resolver list and supports type references.

Example with a trusted application-defined expression:

```java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

String value = parser.parseExpression(
        "new java.lang.String('hello')")
        .getValue(context, String.class);

// hello
```

For application classes, use the fully qualified name if TypeLocator does not yet have an appropriate import prefix:

```text
new com.example.Address('Ho Chi Minh City', 'VN')
```

Switching to StandardEvaluationContext just for constructors means moving to SpEL's broader feature set. This context also permits type references, method invocations, bean references, and other capabilities depending on configuration. Use it only when expressions come from trusted sources and those broad permissions are intentional.

Do not use StandardEvaluationContext to evaluate expressions supplied by end users or untrusted external systems. Constructor and method invocations can execute behavior of the application or libraries on the classpath.

## 9. Restricting Constructors in a Full Context

If an application needs StandardEvaluationContext for certain features but does not want to allow arbitrary constructors, you can configure an allow-list constructor resolver or provide a specialized EvaluationContext for approved constructors only.

Example configuration approach:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

// Register only an application-controlled ConstructorResolver.
// The resolver must reject all types/constructors outside the allow-list.
context.setConstructorResolvers(
        List.of(new ApprovedConstructorResolver()));
```

`ApprovedConstructorResolver` here is an application-written implementation; SpEL does not ship a general-purpose allow-list resolver out of the box. The resolver must validate the target type, constructor signature, and arguments. If type references are needed, also restrict TypeLocator so expressions cannot reference classes out of scope.

A custom resolver only restricts constructors. It does not automatically restrict method invocation, property access, static methods, bean references, or object graph traversal. Each capability must be controlled separately.

If the goal is solely data binding or property filtering, using SimpleEvaluationContext remains the better design.

## 10. Constructor Restrictions Are Not an Absolute Security Guarantee

Spring describes SimpleEvaluationContext as a best-effort feature-restricted context. Excluding constructors, type references, and bean references narrows the expression capability surface, yet does not guarantee that expressions from untrusted sources are always safe.

Expressions can still access properties or invoke instance methods or functions if the configured context permits them. A getter or method can have side effects, read sensitive data, or perform expensive operations. Root objects, nested objects, PropertyAccessors, MethodResolvers, variables, and functions can all expose additional behavior.

When evaluating user-supplied expressions:

- Supply only root objects/variables with minimal data and behavior.
- Prefer dedicated DTOs over full entities or services.
- Enable instance methods only when truly necessary; do not register broad method resolvers arbitrarily.
- Do not place broadly privileged factory functions in the context.
- Audit PropertyAccessors and methods for side effects.
- Limit expression length and complexity per application requirements.
- Do not treat SimpleEvaluationContext as an absolute security sandbox.

## 11. Testing Constructor Restrictions

Unit tests can be written to prove constructor expressions fail in SimpleEvaluationContext and succeed in StandardEvaluationContext for trusted expressions:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.expression.Expression;
import org.springframework.expression.spel.SpelEvaluationException;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class SimpleEvaluationContextConstructorTest {

    private final SpelExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void constructorReferenceIsNotSupportedBySimpleContext() {
        Expression expression = parser.parseExpression(
                "new java.lang.String('hello')");

        SimpleEvaluationContext context =
                SimpleEvaluationContext.forReadOnlyDataBinding().build();

        assertThrows(
                SpelEvaluationException.class,
                () -> expression.getValue(context, String.class));
    }

    @Test
    void trustedConstructorReferenceWorksWithStandardContext() {
        Expression expression = parser.parseExpression(
                "new java.lang.String('hello')");

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        assertEquals(
                "hello",
                expression.getValue(context, String.class));
    }
}
```

The first test verifies SimpleEvaluationContext's restriction. The second test illustrates StandardEvaluationContext's capability; use it in tests only with fixed, trusted expressions.

You can also assert the constructor resolver list:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

assertTrue(context.getConstructorResolvers().isEmpty());
```

These tests verify context behavior and configuration, not expression content quality.

## 12. Common Errors and How to Handle Them

| Symptom | Cause | How to Handle |
|---|---|---|
| `new Type(...)` fails in SimpleEvaluationContext | Context provides no ConstructorResolver. | Create the object in Java or use an explicitly registered factory. |
| `T(Type)` reports type not found | SimpleEvaluationContext does not support type references. | Avoid type references or use a full context for trusted expressions. |
| Builder has no method to enable constructors | Constructor support is excluded by design. | Do not look for a builder toggle; choose an alternative design. |
| `withInstanceMethods()` still disallows `new` | That option only enables the instance method resolver. | Distinguish method invocation from constructor invocation. |
| Factory function is not called | Method not registered or function name mismatch. | Register Method/MethodHandle via `setVariable()` and call as `#functionName(...)`. |
| Factory can create unwanted objects | Registered function is too broad or lacks argument checks. | Provide only specialized factories and validate inputs. |
| Switching to StandardEvaluationContext expands expression privileges | Full context enables many more features than constructors. | Use only with trusted expressions and explicit access controls. |
| Assuming SimpleEvaluationContext is completely safe | Restrictions are best-effort; methods/properties may still have side effects. | Restrict the object graph, accessors, resolvers, variables, and functions. |

## 13. Decision Workflow

1. Determine whether the expression truly needs to create a new instance or only read/write an existing object.
2. If the object is known beforehand, create it in Java and pass it via the root object or a variable.
3. If a parameterized creation operation is needed, consider a narrow factory method registered as a function.
4. If only reading/writing properties is needed, keep SimpleEvaluationContext with minimal privileges.
5. If constructor invocation is needed in a trusted expression, consider StandardEvaluationContext.
6. If using StandardEvaluationContext while wanting to restrict constructors, implement an allow-list ConstructorResolver and restrict TypeLocator appropriately.
7. Separately audit method invocation, property access, bean references, and objects exposed by the context.
8. Write tests confirming constructors are rejected in SimpleEvaluationContext and tests for the chosen alternative.

## 14. Key Takeaways

- SimpleEvaluationContext intentionally excludes constructor references `new Type(...)`, type references `T(...)`, and bean references `@beanName`.
- `SimpleEvaluationContext.getConstructorResolvers()` always returns an empty list; the builder has no option to enable constructors.
- `withInstanceMethods()` only enables restricted instance method invocation, not constructors or static methods.
- Creating objects in Java and passing them via the root object or variables is a straightforward alternative.
- A factory Method/MethodHandle can be registered as a function if only a controlled creation action is needed.
- StandardEvaluationContext supports constructors via its default resolver, while also opening up many other SpEL capabilities.
- An allow-list ConstructorResolver can be used in a custom context when constructor control is genuinely needed.
- SimpleEvaluationContext is a best-effort feature restriction, not an absolute security sandbox.

## References

- [Spring Framework Reference — Understanding EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [EvaluationContext API — Constructor Resolvers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
