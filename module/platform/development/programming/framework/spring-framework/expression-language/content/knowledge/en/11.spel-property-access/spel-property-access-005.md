# Nonexistent Properties and Evaluation Errors

## Objectives

When SpEL accesses a property, the expression must find a way to read that property on the current object. If the property name is wrong, the model does not provide the property, or the EvaluationContext lacks a suitable PropertyAccessor, evaluation can fail at runtime.

The key distinction is between a **nonexistent property**, an **existing property that cannot be read**, and a **null intermediate object**. These three cases have different causes and fixes. The safe navigation operator only handles a null receiver; it does not make a nonexistent property valid.

After this lesson, you can:

- Recognize errors when SpEL fails to resolve a property.
- Distinguish syntax errors, property access errors, and errors caused by null data.
- Inspect JavaBean getters, fields, root object types, and PropertyAccessors.
- Understand the impact of StandardEvaluationContext and SimpleEvaluationContext.
- Use safe navigation in the right places without masking model errors.
- Write tests to catch property errors before deployment.

## 1. When is a property considered nonexistent?

Suppose the root object is a Customer:

~~~java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }
}
~~~

The following expression can read the name property:

~~~text
name
~~~

Meanwhile, the following expression requests another property:

~~~text
email
~~~

If Customer does not provide an email property and no PropertyAccessor in the EvaluationContext can read it, SpEL cannot complete the evaluation. Typically, the getValue call will throw a SpelEvaluationException.

A nonexistent property can stem from several causes:

- Misspelling the property name, such as emailAddress instead of email.
- Renaming a field or getter in Java but forgetting to update the SpEL string.
- Using the wrong root object; the expression expects Customer but actually receives Account.
- The getter is missing, does not conform to JavaBean rules, or is inaccessible to the accessor in use.
- A custom PropertyAccessor is not registered or does not recognize that property.
- The EvaluationContext is configured more restrictively than the environment where the expression was originally written.

Because SpEL typically receives property names as strings, the Java compiler cannot guarantee that all references inside expressions are updated when the model changes. A refactor that renames a getter may compile cleanly yet cause an expression stored in configuration to fail at runtime.

## 2. Successful parsing does not mean the property is valid

SpEL typically has two phases:

1. **Parse:** the parser checks the expression syntax and creates an Expression object.
2. **Evaluate:** the Expression is evaluated with a specific root object and EvaluationContext.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("email");
~~~

The parse line can succeed because email is a syntactically valid property name. The parser does not necessarily know whether the actual root object will be Customer, Account, or another type of object. Property resolution usually happens when the expression is evaluated:

~~~java
String value = expression.getValue(context, customer, String.class);
~~~

If customer does not have an email property and the context has no accessor that provides that property, the error appears at the getValue step.

Therefore, testing parsing alone is not enough to confirm an expression can run. For expressions that depend on a model, you must test evaluation against representative root objects and the exact type of EvaluationContext used by the application.

## 3. Property exists but cannot be read

A property can exist in a class yet still be unreadable via SpEL. SpEL does not access every field or method under a single uniform rule; access depends on the PropertyAccessor configured in the context.

For JavaBeans, properties are typically represented by getters:

~~~java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }
}
~~~

Expression reading the property:

~~~text
name
~~~

Things to check:

- Whether the property name follows JavaBean rules.
- Whether the getter has the expected signature and return type.
- Whether the getter or field has visibility compatible with the accessor.
- Whether the class is proxied or wrapped by another object such that the actual runtime root type differs from expectations.
- Whether the context has the corresponding PropertyAccessor.

For a Boolean property, a JavaBean may use a getter of the form isActive(). Do not guess the property name from the field name if the class has custom getters. Inspect the actual model and the rules of the running accessor.

### Fields and getters are not the same

A private field named email does not automatically guarantee every EvaluationContext can read it. ReflectivePropertyAccessor in standard configuration can support JavaBean properties and fields according to its access rules, whereas SimpleEvaluationContext may use DataBindingPropertyAccessor with data-binding restrictions. A custom PropertyAccessor may also apply different rules.

If you want an expression to read a property, design an explicit public getter or provide a dedicated accessor. Do not rely on an internal field happening to be readable in one specific context.

## 4. Distinguishing a nonexistent property from a null object

The following two situations differ:

~~~text
customer.email
customer?.email
~~~

- If customer is null, the first expression can fail when attempting to access email on null.
- If customer is not null but lacks the email property, neither expression can read that property.

The safe navigation operator **?.** protects an access operation when the object on the left is null. It does not ignore property resolution failures on an existing object.

For example, if Customer has a name property while address may be null:

~~~text
address?.city
~~~

When address is null, the result of the access step is null. When address exists, SpEL still must find the city property on that object.

If the city property does not exist, safe navigation cannot fix the error. You must fix the property name, model, or accessor.

### Safe navigation on multi-level paths

For a path with multiple intermediate objects that may be null, place safe navigation at each step that needs protection:

~~~text
order?.customer?.address?.city
~~~

Each operator protects the receiver immediately before it. Do not assume a single ?. at the start of a path automatically makes all subsequent steps safe against null. Clearly identify which objects can be null and test each scenario.

### Elvis does not handle a missing property

The Elvis operator can supply a default value when the left-hand side evaluates to null:

~~~text
customer.name ?: 'Customer'
~~~

If name exists and has a null value, the expression can use the default value. However, if the name property cannot be resolved, SpEL still raises an error before Elvis can pick the fallback value.

Similarly:

~~~text
customer?.nickname ?: 'Customer'
~~~

This syntax can handle a null customer or null nickname if the nickname property exists and is readable. It does not turn a nonexistent property into a valid one.

## 5. Checking each segment of a property path

A nested path can consist of multiple steps:

~~~text
order.customer.address.city
~~~

If evaluation fails, city is not necessarily the cause. The error might occur at customer, address, or city. An effective diagnostic technique is checking each segment in order:

~~~text
customer
customer.address
customer.address.city
~~~

With order as the root object, each expression above helps identify the first step that cannot be read.

Check:

1. Is the root object of the type the expression expects?
2. Is the first property readable?
3. Is the returned value of the expected object type?
4. Is an intermediate object null?
5. Does the next property exist and is it supported by the accessor?

Do not fix an expression by blindly adding safe navigation everywhere without identifying the cause. If a property name is misspelled, safe navigation does not restore the original intent.

## 6. Impact of EvaluationContext

EvaluationContext determines how SpEL resolves properties and methods. Two different contexts can evaluate the same expression with different outcomes.

### StandardEvaluationContext

StandardEvaluationContext is flexible and typically uses ReflectivePropertyAccessor to read properties via reflection. It can be extended with custom PropertyAccessors and other resolvers.

When an expression works in this context but fails in another environment, compare the accessor lists and actual configurations. Do not assume every context has identical access capabilities.

### SimpleEvaluationContext

SimpleEvaluationContext is designed for data-binding scenarios with a more restricted capability set. Example read-only context:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

This context is suitable when an application only needs to read data through supported accessors. A property that is readable in a broader reflection context may not be accessible in a restricted data-binding context, depending on the model and accessors.

If the application has a custom PropertyAccessor, register it in the factory creating the context and use that same factory in both production and tests. This prevents tests from validating a configuration different from the real one.

### Custom PropertyAccessor

An application can use a PropertyAccessor to provide properties from a custom source or structure. For example, an accessor can read attributes from a dynamic configuration object or a wrapper.

When using a custom accessor, check two possibilities:

- Whether the accessor recognizes the target object and property name in the canRead step.
- Whether the read method actually returns the right value and expected data type.

If canRead returns false, SpEL can try another accessor. If no accessor can read the property, evaluation fails. If the accessor recognizes the property but the read operation itself throws an error, examine the accessor's logic and input data.

## 7. Reading SpEL errors and handling exceptions

Errors during SpEL evaluation are typically represented by SpelEvaluationException, a type of Spring Expression EvaluationException. The error message usually provides information about the operation that failed, the property name, or the relevant expression position.

Example error handling at an application boundary:

~~~java
try {
    String email = expression.getValue(context, customer, String.class);
    return email;
} catch (SpelEvaluationException ex) {
    // Log evaluation error with expression ID and safe context.
    throw new InvalidRuleException("Unable to evaluate property in rule", ex);
}
~~~

Handling should match the role of the expression:

- For fixed expressions in source code, an error may indicate a bug or an un-updated model change.
- For expressions in configuration, an error may be an invalid configuration and should be caught at load time.
- For administrator-created expressions, return a clear validation error before activation.
- For expressions evaluated during a request, convert the error into an appropriate business response and log enough to trace it.

Do not catch every RuntimeException and return null. That approach can turn a model error into a seemingly valid result and cause the system to make wrong decisions.

Nor should you expose stack traces or sensitive root-object data to end users. Log the expression ID, version, error type, and correlation ID; only log input data when it is confirmed safe to log.

## 8. Testing property errors

A good test suite should verify both readable properties and unreadable cases.

Example model:

~~~java
public class Customer {
    private String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Testing an existing property:

~~~java
@Test
void readsExistingProperty() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("name");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Customer customer = new Customer("Lan");

    assertEquals("Lan", expression.getValue(context, customer, String.class));
}
~~~

Testing a nonexistent property:

~~~java
@Test
void failsWhenPropertyDoesNotExist() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("email");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Customer customer = new Customer("Lan");

    assertThrows(
        SpelEvaluationException.class,
        () -> expression.getValue(context, customer)
    );
}
~~~

Testing intermediate null and safe navigation:

~~~java
@Test
void handlesNullIntermediateObject() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("address?.city");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Customer customer = new Customer("Lan");

    assertNull(expression.getValue(context, customer));
}
~~~

The last example assumes Customer has an address property and the address value is currently null. If the address property does not exist, safe navigation cannot help the expression read that property. Ensure the model in tests accurately reflects the scenario being tested.

Your expression test suite should include the following cases:

| Case | What to verify |
|---|---|
| Valid property with value | Returns the expected value and type |
| Valid property that is null | Null is handled per the contract |
| Nonexistent property | Error is clearly detected |
| Unreadable getter | Accessor/context reflects the restriction accurately |
| Null root object | Expression behaves as defined |
| Null intermediate object | Safe navigation is placed at the right steps |
| Multi-level property path | Pinpoints the exact failing segment |
| Context changed | Expression still works or fails intentionally |
| Model renames property | Regression test catches stale references |

## 9. Diagnostic workflow in an application

When an expression starts failing in a live environment, follow this sequence:

1. **Get the exact expression and version.** Ensure you are investigating the exact string loaded in the failing instance.
2. **Identify the actual root object.** Check the class of the object passed to getValue and avoid logging full sensitive data.
3. **Separate parse from evaluate.** Determine whether the error happens when creating the Expression or when calling getValue.
4. **Inspect the property path step by step.** Start from the root and expand segment by segment until identifying the first unreadable property.
5. **Check the model and accessors.** Cross-check getters, fields, visibility, custom PropertyAccessors, and EvaluationContext type.
6. **Check null separately.** Determine which object is null; only use safe navigation when null is an acceptable scenario.
7. **Create a regression test.** Put the failing root object, context, and data into a test so the bug does not return.
8. **Deploy changes with control.** If the expression resides in configuration, validate the new version before activation and maintain rollback capability.

If the error appears only on some instances, compare the actual model, application version, context configuration, and expression version across instances. One node may be running an older model or configuration.

## 10. Preventing errors when models change

Property paths in SpEL form a runtime contract with the Java model. When renaming or restructuring properties, search every place where expression strings are stored:

- Annotations and XML configuration.
- Properties, YAML, or JSON files.
- Databases or rule management tables.
- Expression management systems.
- Test fixtures and sample data.
- Expressions dynamically constructed in Java.

If expressions are managed centrally, store the root type, purpose, version, and list of properties used alongside them. You can validate all expressions against sample root objects on application startup or when configuration is updated.

For large model changes, run regression tests across the entire set of related expressions. A test that merely parses strings will not catch broken property paths; expressions must be evaluated against representative objects.

## 11. Review checklist

Before accepting a property-access expression, verify:

- [ ] Root object has the right type according to the expression contract.
- [ ] Property names match the actual model and getters.
- [ ] Properties are readable by the PropertyAccessor in use.
- [ ] EvaluationContext in tests matches the production configuration.
- [ ] Intermediate objects that can be null are handled separately.
- [ ] Safe navigation is used only where a null receiver is acceptable.
- [ ] Elvis is not used with the expectation of hiding a nonexistent property.
- [ ] Tests exist for valid properties, missing properties, and null objects.
- [ ] Parse errors and evaluation errors are distinguished.
- [ ] Logs contain the expression ID and necessary tracing info without exposing sensitive data.
- [ ] Model changes check SpEL strings stored outside source code.

## Conclusion

Property errors in SpEL usually appear when property names are wrong, models change, root objects are unexpected, or the EvaluationContext lacks an appropriate accessor. Successful parsing only confirms syntax, while whether a property is readable is usually determined when evaluating against an actual object. Distinguish missing properties from null receivers, check each segment of the path, use safe navigation in the right places, and test with the same context as production. That way, runtime errors can be caught early and diagnosed to their specific root cause.
