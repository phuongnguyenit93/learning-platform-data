# Assignment Restrictions in SimpleEvaluationContext

## Objectives

After this lesson, you will be able to explain why Spring Expression Language (SpEL) restricts assignment operations in SimpleEvaluationContext; distinguish property assignment, variable assignment, and calling the setValue API; choose an appropriate read-only or read-write configuration; and handle errors when an expression attempts to modify data not permitted by the context.

## 1. Why Restrict Assignment Operations?

SpEL does not only read values. Depending on the expression and EvaluationContext, it can also modify properties of objects:

~~~text
name = 'An'
~~~

An expression with write permissions can mutate the state of objects passed in by the application. If expressions come from configuration or external sources, overly broad write permissions can lead to unintended data modification.

SimpleEvaluationContext is designed for cases that only need a subset of SpEL capabilities, such as data binding and property-based filtering. The application must explicitly select the scope of property and method access. As a result, reading and writing can be restricted to what is needed.

Point to remember: SimpleEvaluationContext does not always forbid all write operations. Write capability depends on the context type and configured PropertyAccessor.

## 2. Three Concepts to Distinguish

In SpEL, there are three approaches that are easily confused:

1. **Property assignment in an expression:** using the equals operator to modify a property of the root object or an accessible object.
2. **Variable assignment in an expression:** using the equals operator with a variable prefixed by a hash sign, such as updating a variable in EvaluationContext.
3. **Assignment from Java:** the application calling setVariable or Expression.setValue directly via the API.

These three approaches go through different mechanisms. The fact that a context allows one kind of operation does not mean all other kinds of operations are also permitted.

## 3. Property Assignment in an Expression

Suppose we have a simple JavaBean:

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

You can use the following expression to modify the property:

~~~text
name = 'An'
~~~

When evaluating the expression with a Customer as the root object, SpEL needs a PropertyAccessor capable of writing the name property.

If you create a read-only context:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

this context uses DataBindingPropertyAccessor in read-only mode and disables the assignment operator in expressions. Therefore, an expression requesting a property write will not be accepted.

If the application genuinely needs two-way data binding, you can create a read-write context:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name = 'An'");

Customer customer = new Customer();

String assignedName =
    expression.getValue(context, customer, String.class);
~~~

After evaluation, customer's name property is updated to An. Write capability comes from DataBindingPropertyAccessor in read-write mode.

Use this configuration only when business logic genuinely requires expressions to mutate properties. For filters or rules that only need to read data, a read-only context is more appropriate.

## 4. Variable Assignment Differs from Property Assignment

A variable in EvaluationContext is typically referenced with a hash prefix:

~~~text
#currentName
~~~

The application can register a variable from Java:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

context.setVariable("currentName", "An");
~~~

Then the expression can read the variable:

~~~text
#currentName
~~~

However, SimpleEvaluationContext does not support variable assignment inside an expression. For example:

~~~text
#currentName = 'Binh'
~~~

will be rejected. This is a specific limitation of SimpleEvaluationContext, even when the context is configured for read-write property access.

If you need to update a variable, perform it from Java code:

~~~java
context.setVariable("currentName", "Binh");
~~~

Therefore, you must distinguish:

| Operation | SimpleEvaluationContext |
|---|---|
| Reading a variable with #name | Yes |
| Registering or updating a variable via context.setVariable from Java | Yes |
| Assigning a variable with expression #name = value | Not supported |
| Reading a property via read-only data binding | Yes |
| Writing a property via an expression with read-only data binding | No |
| Writing a property with read-write data binding | Yes, if the property is writable |

## 5. Assignment, Increment, and Decrement Operators

In Spring versions that support the EvaluationContext assignment flag, when isAssignmentEnabled returns false, the following operators are disabled in expressions:

- Assignment: single equals sign.
- Increment: double plus operator.
- Decrement: double minus operator.

Example:

~~~text
#counter = #counter + 1
#counter++
#counter--
~~~

The expressions above cannot be used to update a variable on SimpleEvaluationContext. For property assignment, whether it is allowed also depends on the PropertyAccessor's write permission.

SimpleEvaluationContext.forReadOnlyDataBinding() creates a read-only context and disables assignment. SimpleEvaluationContext.forReadWriteDataBinding() permits writing properties via data binding and enables assignment in expressions by default. You can disable assignment on the builder of matching contexts using withAssignmentDisabled().

Example:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadWriteDataBinding()
        .withAssignmentDisabled()
        .build();
~~~

This configuration keeps the read-write data-binding accessor while disabling assignment, increment, and decrement operators in expressions. When a comprehensive read-only policy for properties is needed, choose forReadOnlyDataBinding() from the start.

Version note: the isAssignmentEnabled and Builder.withAssignmentDisabled APIs were added in Spring Framework 5.3.38. If your project uses an older version, check the Javadoc for that exact version before using these methods.

## 6. Assignment via Expression.setValue

Besides the assignment operator inside the expression string, SpEL provides the Expression.setValue API so the application can proactively write a value to a property:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

Customer customer = new Customer();

EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

expression.setValue(context, customer, "Binh");
~~~

Here, the expression only identifies the name property. Java code calls setValue to instruct SpEL to write the value Binh into that property.

This is a write operation initiated from Java, not an expression assigning a variable itself. It still requires a PropertyAccessor that supports writing, and the property must be updatable.

Do not infer that because SimpleEvaluationContext forbids variable assignment in expressions, it also removes setVariable or all setValue APIs. Examine the exact operation being invoked and the permissions provided by the accessor.

## 7. Assignment via a Custom PropertyAccessor

SimpleEvaluationContext allows the application to supply its own PropertyAccessor to control how data is read and written.

Example of creating a context from a custom accessor:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forPropertyAccessors(customPropertyAccessor)
        .build();
~~~

With the forPropertyAccessors factory, assignment is enabled by default in expressions. If you do not want expressions to modify properties directly, you can disable it:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forPropertyAccessors(customPropertyAccessor)
        .withAssignmentDisabled()
        .build();
~~~

The custom accessor decides which properties can be read or written and how the operation is executed. This is a useful option when the data is not a standard JavaBean, such as a key-value structure or a specialized data model.

Do not pass a standard ReflectivePropertyAccessor into SimpleEvaluationContext. SimpleEvaluationContext is designed to use DataBindingPropertyAccessor or clearly scoped custom accessors.

## 8. How to Handle Rejected Assignments

If an expression attempts to write to a read-only property or perform an unsupported assignment, SpEL may throw SpelEvaluationException or a corresponding evaluation error.

For example, the application should catch errors at the layer invoking the expression:

~~~java
try {
    expression.getValue(context, customer);
}
catch (EvaluationException ex) {
    // Log appropriately and handle the error according to application rules.
}
~~~

Do not catch all exceptions and silently treat a failed assignment as successful. The application must distinguish errors caused by the context disallowing writes, nonexistent properties, failed type conversion, or setters throwing errors themselves.

If the write operation is mandatory, verify the context and accessor configuration before putting the expression into use. If writes are disallowed, keep the context read-only and treat an invalid expression as a configuration error.

## 9. SimpleEvaluationContext Is Not StandardEvaluationContext

The two contexts have different capability scopes:

| Capability | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Reading properties | Yes, requires choosing an accessor | Yes, flexible configuration |
| Writing properties | Can be enabled with a read-write accessor | Yes, if the accessor permits |
| Variable assignment inside expressions | Not supported | Yes |
| Setting variables from Java via setVariable | Yes | Yes |
| Referencing Java types via T(...) | Not supported | Configurable |
| Creating objects via new | Not supported | Configurable |
| Referencing beans via @beanName | Not supported | Configurable |
| Custom property accessors | Yes | Yes |
| Configuring method resolvers | Yes, via an opt-in mechanism | Yes, more flexible |

If you only need to filter data or bind certain properties, SimpleEvaluationContext helps narrow an expression's capabilities. If full SpEL features are needed, StandardEvaluationContext may be more suitable, though you must tightly control the root object, accessors, resolvers, and expression source.

Choosing StandardEvaluationContext merely to bypass a SimpleEvaluationContext restriction will significantly expand the privileges an expression can use. Clearly identify the requirements before changing the context.

## 10. Restricting Write Permissions Does Not Equal an Absolute Security Sandbox

SimpleEvaluationContext narrows the language scope and access permissions, yet it does not guarantee that expressions from untrusted sources will be completely safe.

Even when only reading properties, a getter or an accessor-like method can still cause side effects. For example, a zero-argument method that deletes a file or removes an element from a queue can look like a property when accessed via SpEL.

Therefore:

1. Provide only the root object and variables that are strictly necessary.
2. Prefer dedicated data types that expose only simple properties.
3. Prefer immutable objects when only reading is needed.
4. Inspect getters and accessors that can be invoked.
5. Enable read-write only when there is a clear business requirement.
6. Do not treat SimpleEvaluationContext as a mechanism for running arbitrary user-submitted expressions.

Read-only only controls property assignment. It does not prove that every read operation is free of side effects.

## 11. Combined Example: Choosing Read or Write Mode

~~~java
ExpressionParser parser = new SpelExpressionParser();
Customer customer = new Customer();

// Read-only case
EvaluationContext readOnly =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression readName = parser.parseExpression("name");
String currentName =
    readName.getValue(readOnly, customer, String.class);

// Property write-enabled case
EvaluationContext readWrite =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

Expression assignName =
    parser.parseExpression("name = 'An'");

String assignedName =
    assignName.getValue(readWrite, customer, String.class);

// Update context variable from Java
readWrite.setVariable("operator", "admin");
~~~

In the example, the read-only context is used to retrieve the name. The read-write context is used to evaluate the property assignment expression. The operator variable is registered directly from Java.

If you replace the property assignment expression with a variable assignment expression such as #operator = 'guest', SimpleEvaluationContext still does not support that operation. Use setVariable from Java to update variables.

## 12. Key Takeaways

SimpleEvaluationContext restricts assignment based on configuration and operation type. forReadOnlyDataBinding() provides property read access and disables assignment in expressions. forReadWriteDataBinding() permits reading and writing properties via DataBindingPropertyAccessor. Custom accessors can also govern write permissions; the builder can disable assignment when needed.

Variable assignment inside expressions is not supported by SimpleEvaluationContext, even when the context permits writing properties. However, the application can still register or update variables using setVariable from Java. Expression.setValue is a separate property-writing API and requires an accessor that supports writing.

Choose read or write permissions according to actual needs, distinguish property assignment from variable assignment, and handle evaluation errors explicitly. SimpleEvaluationContext helps narrow SpEL's privileges, yet you must still control which objects and methods expressions can access.

## References

- [Spring Framework Reference — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework Reference — Assignment Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)