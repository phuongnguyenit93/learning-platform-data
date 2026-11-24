# Read-Only and Read-Write Data Binding in SpEL

Spring Expression Language (SpEL) can read and update object properties through an EvaluationContext. For data binding scenarios, Spring provides **SimpleEvaluationContext** along with two important factory methods:

- **forReadOnlyDataBinding()** creates a context that only allows reading properties.
- **forReadWriteDataBinding()** creates a context that allows reading and writing properties.

Both use **DataBindingPropertyAccessor** to access public properties according to data binding conventions. This choice helps restrict SpEL's capabilities when an application only needs to read data or update certain object attributes.

Read-only and read-write here refer to the permission to assign values to properties in an expression. They do not turn SpEL into a safe sandbox for untrusted expressions; reading a property can still invoke an accessor with side effects.

## 1. SimpleEvaluationContext for data binding

SpEL has two commonly used EvaluationContext implementations:

- **StandardEvaluationContext** provides SpEL's full features and customization capabilities, suitable for internal configuration scenarios requiring flexible access.
- **SimpleEvaluationContext** provides only a subset of features, geared toward simple conditions, property-based filtering, and data binding.

SimpleEvaluationContext requires the application to explicitly choose the required level of property and method access. By default, this context does not support type references, constructor invocations, or bean references. Method invocation is also not enabled by default.

When the goal is simply reading or updating data on objects, the two data-binding factory methods configure the context concisely and clearly express the intended access permissions.

## 2. Read-only data binding

Creating a read-only context:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

This factory method configures DataBindingPropertyAccessor in read-only mode and disables assignment in expressions.

Properties can be read from the root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("customer.address.city");

String city = expression.getValue(
        context,
        order,
        String.class
);
~~~

In the example, order is the root object passed to getValue(). SpEL reads customer, address, and city in sequence. The expression does not need write permissions to perform these operations.

You can also read a simple property:

~~~text
name
~~~

Or a nested property:

~~~text
customer.address.postalCode
~~~

Read-only data binding is suitable when expressions are used to display data, generate labels, filter objects, check conditions, or extract values from an object graph.

### 2.1. Read-only prevents assignment in expressions

Example expression with an assignment:

~~~text
name = 'Linh'
~~~

When evaluated with a context created from forReadOnlyDataBinding(), assignment is disabled and the expression cannot update the property.

This helps prevent data-binding expressions from accidentally mutating object state when the task only requires reading data.

It is important to distinguish disallowing writes in an expression from the Java object itself being immutable. A read-only context does not make an object immutable and does not prevent other Java code from updating that object.

### 2.2. When to choose read-only?

Use read-only when:

1. The expression only needs to read properties for display or output generation.
2. The expression is used to evaluate conditions or filter objects.
3. There is no requirement to update objects through SpEL.
4. You want to reduce the chance of expressions mutating data state.
5. You want to configure data binding with the minimum necessary permissions.

If you only need to read properties, prefer read-only rather than enabling read-write and relying on convention that expressions will not assign values.

## 3. Read-write data binding

When properties need to be updated via SpEL, create the context using:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

This factory method configures DataBindingPropertyAccessor in read-write mode. Assignment is enabled by default.

Example class with getter and setter:

~~~java
public class Customer {

    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Expression assigning a value to a property:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("name = 'Linh'");

Customer customer = new Customer();

Object result = expression.getValue(context, customer);

System.out.println(customer.getName()); // Linh
~~~

SpEL uses the root object customer, locates the name property, and invokes DataBindingPropertyAccessor's corresponding write mechanism. The new value is set via the public setter in this example.

Nested properties can be assigned:

~~~text
address.city = 'Ho Chi Minh City'
~~~

Intermediate objects such as address must exist and the target property must be writable. Data binding does not automatically create every nested object if they are null.

### 3.1. Conditions for a property to be writable

DataBindingPropertyAccessor supports public properties according to data-binding conventions:

- When reading, a property can be provided via a public getter or public field.
- When writing, a property requires a public setter or a writable public field.
- A property with only a getter is generally readable but not writable.
- The property name in the expression must match a property supported by the accessor.

Example of a read-only property:

~~~java
public String getDisplayName() {
    return displayName;
}
~~~

An expression can read displayName, but cannot assign to it if the class does not provide a setter or writable public field.

If an expression needs to update multiple attributes, clearly verify whether the object has corresponding setters and whether the state after assignment is valid according to domain rules.

### 3.2. When to choose read-write?

Use read-write when:

1. The application needs to update object properties through expressions.
2. A form or data-binding layer needs to write values into a model.
3. Expressions perform controlled assignments on public properties.
4. Target properties have appropriate setters or public fields.
5. Write permission is an intended part of the functionality, not an unintended side effect.

Read-write only opens property write permissions according to the configured accessor. It does not automatically enable all features of StandardEvaluationContext.

## 4. Comparing read-only and read-write

| Criterion | Read-only | Read-write |
| --- | --- | --- |
| Factory | forReadOnlyDataBinding() | forReadWriteDataBinding() |
| Property accessor | DataBindingPropertyAccessor in read mode | DataBindingPropertyAccessor in read/write mode |
| Reading public properties | Yes | Yes |
| Assigning properties in expressions | Disabled | Enabled by default |
| Setter or writable public field | Not needed for reading | Required on target property when writing |
| Common goals | Display, filtering, validation | Form binding, updating models |
| Constructor expressions | Not supported | Not supported |
| Bean references | Not supported | Not supported |
| Type references T() | Not supported | Not supported |

Both factory methods create a SimpleEvaluationContext. The main differences are the property accessor configuration and assignment permission.

If the application also needs object instantiation, bean references, or other full SpEL features, consider StandardEvaluationContext and restrict the access strategies to match exact needs.

## 5. Root object when using SimpleEvaluationContext

SimpleEvaluationContext is typically created without a default root object. A common pattern is to parse the Expression once and then pass the context along with the root object into each getValue() call.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("customer.address.city");

String firstCity = expression.getValue(
        context,
        firstOrder,
        String.class
);

String secondCity = expression.getValue(
        context,
        secondOrder,
        String.class
);
~~~

The same expression and context can be used with different root objects. This is useful when a data-binding rule is repeatedly applied across multiple objects of the same structure.

Variables can be used if additional data outside the root object needs to be supplied:

~~~java
context.setVariable("requiredRegion", "APAC");
~~~

Expression:

~~~text
region == #requiredRegion
~~~

Here region is a property of the root object; requiredRegion is a variable registered in the context.

## 6. DataBindingPropertyAccessor and property scope

Both data-binding factory methods use **DataBindingPropertyAccessor**. This accessor is designed for application-declared properties, such as JavaBean properties or data types with public accessors.

It does not broadly resolve technical properties on java.lang.Object or java.lang.Class the way ReflectivePropertyAccessor does. The goal is to provide property access for data binding, rather than opening up full reflective property access.

Example:

~~~java
public class Address {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

The expressions:

~~~text
city
city = 'Da Nang'
~~~

can read and write city respectively depending on whether the context was created in read-only or read-write mode.

For custom data types or non-JavaBean structures, you can build a SimpleEvaluationContext using the forPropertyAccessors() factory and register an appropriate PropertyAccessor.

## 7. Customizing SimpleEvaluationContext

In addition to the two built-in data-binding factories, SimpleEvaluationContext's Builder allows configuring several additional capabilities.

### 7.1. Using a custom PropertyAccessor

When data has a custom structure, you can supply an accessor:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forPropertyAccessors(customPropertyAccessor)
                .build();
~~~

You can combine a custom accessor with DataBindingPropertyAccessor if both custom properties and data-binding properties are needed.

### 7.2. Disabling assignment on a custom builder

A context created from forPropertyAccessors() allows assignment by default. If you want read-only behavior, you can disable assignment:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forPropertyAccessors(customPropertyAccessor)
                .withAssignmentDisabled()
                .build();
~~~

For ordinary read-only data binding needs, forReadOnlyDataBinding() is the more direct and clearer choice.

### 7.3. Enabling instance method invocation when truly needed

SimpleEvaluationContext does not enable method resolution by default. The builder can add DataBindingMethodResolver for instance methods:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

This configuration adds the ability to invoke instance methods supported by the resolver. It does not open static method invocation and does not turn the context into StandardEvaluationContext.

Only enable method invocation when the expression genuinely needs it. If the goal is merely reading properties, there is no need to add this capability.

### 7.4. Configuring ConversionService

The builder also allows supplying a custom ConversionService:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

This is useful when input data needs to be converted according to application rules. For example, a string from a form might need to be converted to a numeric type or domain type before being assigned to a property.

ConversionService handles type conversion; it does not replace the property accessor and does not automatically create setters for non-writable properties.

## 8. Distinguishing property assignment and method invocation

Read-write data binding allows assigning properties. That does not mean every method on the object is permitted to be invoked.

SimpleEvaluationContext does not enable a method resolver by default. If instance methods are needed, you must actively add an appropriate resolver, such as withInstanceMethods().

Example of property assignment:

~~~text
name = 'Linh'
~~~

This is a property write operation.

Example of method invocation:

~~~text
changeName('Linh')
~~~

This is a method call and requires a configured method resolver, in addition to the method being accessible.

Do not confuse the two capabilities. A read-write context may allow property assignment while still rejecting method calls because method invocation has not been enabled.

## 9. Read-only does not guarantee getters are side-effect free

Read-only data binding only controls property assignment in expressions. It does not prove that reading a property is a pure operation.

A Java getter can perform actions before returning a value. For example, an accessor-shaped method can write logs, update state, access an external system, or cause other side effects.

Therefore:

- Only pass data types into the root object whose accessors match the expression's purpose.
- Do not treat SimpleEvaluationContext as a safe sandbox for expressions supplied by untrusted users.
- Inspect accessible getters and methods to ensure reading does not cause unintended effects.
- Limit the object graph placed into the context.
- Do not enable method invocation or accessors broader than necessary.

Spring documentation emphasizes that SimpleEvaluationContext only limits a subset of syntax and features. Using read-only does not by itself guarantee an expression is safe.

## 10. Example testing read-only and read-write

Both modes can be verified using JUnit:

~~~java
class DataBindingContextTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void readsPropertyWithReadOnlyContext() {
        SimpleEvaluationContext context =
                SimpleEvaluationContext
                        .forReadOnlyDataBinding()
                        .build();

        Customer customer = new Customer("An");

        String name = parser
                .parseExpression("name")
                .getValue(context, customer, String.class);

        assertEquals("An", name);
    }

    @Test
    void rejectsAssignmentWithReadOnlyContext() {
        SimpleEvaluationContext context =
                SimpleEvaluationContext
                        .forReadOnlyDataBinding()
                        .build();

        Customer customer = new Customer("An");

        assertThrows(EvaluationException.class, () ->
                parser.parseExpression("name = 'Linh'")
                        .getValue(context, customer)
        );
    }

    @Test
    void updatesPropertyWithReadWriteContext() {
        SimpleEvaluationContext context =
                SimpleEvaluationContext
                        .forReadWriteDataBinding()
                        .build();

        Customer customer = new Customer("An");

        parser.parseExpression("name = 'Linh'")
                .getValue(context, customer);

        assertEquals("Linh", customer.getName());
    }
}
~~~

The first test verifies that the property is read. The second test verifies that assignment is blocked in a read-only context. The last test verifies that a read-write context updates the property through the appropriate accessor.

In a real application, test getter-only properties, properties with setters, nested properties, and null intermediate object cases if data can be in that state.

## 11. Common mistakes

1. **Using read-only while still writing assignments:** expressions like name = 'Linh' are not permitted in a read-only context.
2. **Using read-write when the property lacks a setter:** the accessor cannot write a getter-only property if there is no writable public field.
3. **Confusing read-write with StandardEvaluationContext:** read-write is still a SimpleEvaluationContext and does not support constructors, type references, or bean references.
4. **Assuming method invocation is enabled automatically:** a method resolver must be added if instance methods need to be called.
5. **Not passing a root object:** SimpleEvaluationContext is typically used by passing the root object to getValue(context, rootObject).
6. **Null intermediate objects:** nested property paths can fail if an intermediate object does not exist.
7. **Assuming read-only prevents all side effects:** getters can still perform actions.
8. **Using an unsuitable accessor:** custom properties require a corresponding PropertyAccessor.
9. **Uncontrolled sharing of a mutable context:** variables or context configuration can affect multiple evaluations.
10. **Treating SimpleEvaluationContext as a sandbox:** the context restricts features, but does not guarantee expressions from untrusted sources are safe.

## 12. Quick takeaways

- **SimpleEvaluationContext.forReadOnlyDataBinding()** creates a context that reads properties and disables assignment.
- **SimpleEvaluationContext.forReadWriteDataBinding()** creates a context that reads/writes properties and enables assignment by default.
- Both use **DataBindingPropertyAccessor**.
- Reading properties generally requires a public getter or public field; writing requires a public setter or writable public field.
- Read-write only opens property write permissions according to the accessor; it does not open all SpEL features.
- SimpleEvaluationContext does not support type references, constructor invocations, or bean references.
- Method invocation is not enabled by default; an instance method resolver can be added when genuinely needed.
- SimpleEvaluationContext usually receives the root object via getValue(context, rootObject).
- PropertyAccessor, assignment, and ConversionService can be customized via the Builder.
- Read-only does not guarantee getters are side-effect free and is not a sandbox for untrusted expressions.
- Choose read-only if only reading is needed; choose read-write only when the feature genuinely needs to update properties.

## 13. Official references

- [Spring Framework — EvaluationContext and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [DataBindingPropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html)
- [DataBindingMethodResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingMethodResolver.html)
- [Spring Framework — Security Considerations for EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html#expressions-evaluation-context-security)
