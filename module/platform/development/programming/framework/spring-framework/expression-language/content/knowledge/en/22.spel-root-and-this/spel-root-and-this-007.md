# Null Root Object and Handling Strategies

In Spring Expression Language (SpEL), the **root object** is the base object an expression uses when reading properties or calling methods without specifying another variable or object. The root object can be supplied when creating an **EvaluationContext**, or passed directly into each call to **Expression.getValue(...)**.

The root object is not required to be non-null. However, if an expression directly accesses a property or calls a method on a null root object, evaluation will fail. Therefore, the application must determine clearly whether null is a valid state or invalid input data, and then choose an appropriate handling strategy.

## How is the root object supplied?

There are two common ways to set the root object for an evaluation pass.

The first way is to set the root object on StandardEvaluationContext:

~~~java
Customer customer = new Customer("An");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(customer);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(context, String.class);
~~~

In the example, **customer** is the context's root object. The expression **name** reads the name property from that object.

The second way is to pass the root object at evaluation time:

~~~java
Expression expression = parser.parseExpression("name");

String name =
        expression.getValue(context, customer, String.class);
~~~

This approach is useful when the same Expression is evaluated against multiple different objects. The context can hold shared variables and configuration, while the root object varies per call.

## What happens when the root object is null?

If the root object is null, SpEL can still evaluate expressions that do not need to access the root object, such as literals or variables declared in the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(null);
context.setVariable("greeting", "Hello");

ExpressionParser parser = new SpelExpressionParser();

String literal =
        parser.parseExpression("'Spring'")
                .getValue(context, String.class);

String greeting =
        parser.parseExpression("#greeting")
                .getValue(context, String.class);
~~~

The two expressions above do not need to read properties from the root object, so they can still return values. The expression **#root** can also be used to check the current root reference.

Conversely, an expression that directly accesses a property like **name** or calls a method like **getName()** requires a target object. If the root object is null, SpEL has no object on which to perform the operation and will raise an evaluation error.

~~~java
Expression expression =
        parser.parseExpression("name");

String name =
        expression.getValue(context, String.class);
~~~

If the context has no root object, the expression above cannot read the name property. This is an error at the evaluation stage, not a syntax error: the string **name** is still a valid expression, but there is no suitable object to evaluate against.

## Distinguishing a null root object from a null property

These cases are different:

- **Null root object:** there is no root object from which the expression can read properties.
- **Root object exists but a property is null:** a root object is present, but part of the data inside the object graph has no value.
- **Empty collection:** the collection exists but contains no elements.
- **Null collection:** there is no collection to iterate over.

For example, Customer exists but address is null:

~~~java
Customer customer = new Customer("An");
customer.setAddress(null);

context.setRootObject(customer);
~~~

The expression **name** can still read the customer's name. The expression **address.city** will run into trouble because address is null. If the entire customer is null, even reading **name** cannot succeed.

Do not treat null and an empty collection as the same state. An empty collection usually means the data exists but currently has no elements; a null collection can signify data that has not been provided or initialized. Business policy should decide how to interpret these two cases.

## Using #root to check the root object

SpEL provides the special variable **#root** to reference the initial root object of the evaluation pass:

~~~java
Expression expression =
        parser.parseExpression("#root == null");

Boolean isRootNull =
        expression.getValue(context, rootObject, Boolean.class);
~~~

If rootObject is null, the result is true. Using #root lets the expression check the root object explicitly, especially when the expression also has other variables or is inside a collection operation context.

Distinguish **#root** from **#this**:

- **#root** keeps a reference to the initial root object throughout the evaluation pass.
- **#this** is the current object at the position where the expression is being evaluated; in selection or projection, it can be the current element of the collection.

In a simple top-level expression, #this usually coincides with the root object. However, when entering a collection operation or a nested evaluation context, do not treat these two variables as equivalent.

## Null-safe navigation with the ?. operator

SpEL supports the **null-safe navigation operator**, **?.**. This operator allows accessing a property or calling a method on a potentially null object without throwing an error solely because the target object is null.

For example, instead of accessing **name** directly, you can write:

~~~java
Expression expression =
        parser.parseExpression("#root?.name");

String name =
        expression.getValue(context, rootObject, String.class);
~~~

If rootObject is null, the name access returns null. If rootObject exists, SpEL reads the name property as usual.

Null-safe navigation can be used for nested property chains:

~~~java
Expression expression =
        parser.parseExpression(
                "#root?.customer?.address?.city");

String city =
        expression.getValue(context, rootObject, String.class);
~~~

Each **?.** segment guards the next access step if the object on the left is null. This style is appropriate when each link in the object graph may be absent.

### Placing null-safe operators at every step

Null-safe navigation only guards the operation immediately following the operator. If a step returns null and the expression continues accessing properties with a regular dot, an error can still occur.

Example:

~~~text
#root?.customer.address.city
~~~

If root exists but customer is null, the subsequent access to address is unprotected. A safer form when both customer and address can be null is:

~~~text
#root?.customer?.address?.city
~~~

Place null-safe navigation at every position where an intermediate value may be null. Do not assume that placing **?.** only at the beginning of the chain automatically makes the rest of the expression safe.

## Using the Elvis operator to provide a default value

If null can be replaced with a valid default value, you can use the **Elvis operator ?:**:

~~~java
Expression expression =
        parser.parseExpression("#root?.name ?: 'Guest'");

String displayName =
        expression.getValue(context, rootObject, String.class);
~~~

If the root object is null or the name property has no value, the expression can return **Guest**. When a name is present, the expression returns that name.

The Elvis operator helps write common cases more concisely than the ternary conditional operator. In SpEL, a null or empty string on the left side can also lead to using the value on the right side. If the application needs to distinguish an empty string from null, use an explicit condition instead of relying on Elvis.

A default value should only be used when it is valid for the business domain. For example, using Guest for a display name may make sense; using a default value for customerId or access permissions can mask missing data and create incorrect behavior.

## Using the conditional operator to decide explicitly

When you need to check the root object before accessing it, you can use the ternary operator:

~~~java
Expression expression =
        parser.parseExpression(
                "#root == null ? 'No customer' : #root.name");

String label =
        expression.getValue(context, rootObject, String.class);
~~~

When root is null, the expression takes the first branch and does not access name. Only when root exists does the expression read the name property.

This style clearly expresses both handling branches and fits when the null state needs a distinct result. If the name property can also be null, add a condition or use null-safe navigation and an appropriate default value.

## Handling nested properties that may be null

An object graph often has multiple property levels. For example, Order has customer, Customer has address, and Address has city. If just one intermediate level is null, deep access using regular dots can fail.

~~~java
Expression expression =
        parser.parseExpression(
                "#root?.customer?.address?.city ?: 'Unknown'");
~~~

This expression returns city if the entire property chain exists and has a value; if a link is null or the final result has no value, Elvis supplies the Unknown label.

If each null state has a different meaning, do not collapse all of them into a single default value. Inspect and classify them in Java or use explicit conditional branches to distinguish:

- No Order.
- Order has no Customer attached.
- Customer has no Address yet.
- Address exists, but city has not been entered.

This distinction is useful when the application needs to display specific messages, write logs, or ask the user to supply missing data.

## Passing variables when there is no root object

An expression does not strictly need a root object if data is provided through variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(null);
context.setVariable("displayName", "An");

Expression expression =
        parser.parseExpression("#displayName ?: 'Guest'");

String result =
        expression.getValue(context, String.class);
~~~

The expression uses #displayName and therefore does not need to read properties from root. This is a suitable organization when inputs are independent parameters that do not belong to a single base object.

However, if a variable holds an object and the expression accesses properties of that variable, the object inside the variable can still be null. In that case, use null-safe navigation or conditional checks just as with the root object.

## Handling a null root in Java before evaluation

Not every null case should be handled inside SpEL. If the root object is required business data, the clearest approach is usually to validate it in Java before calling getValue:

~~~java
Objects.requireNonNull(
        customer,
        "Customer is required");

String name =
        expression.getValue(context, customer, String.class);
~~~

This makes input errors surface early and keeps the expression focused on the logic it needs to perform. It also helps separate input data errors at the application boundary from expression evaluation errors.

You can use a conditional check instead of throwing an exception if the application needs to return a business result:

~~~java
if (customer == null) {
    return "No customer";
}

return expression.getValue(context, customer, String.class);
~~~

Choose the handling approach according to the meaning of null: reject the input, return a default result, skip the operation, or represent an undetermined state.

## Null root collection and empty collection

If the root object itself is a collection, distinguish a null collection from an empty collection:

~~~java
List<String> names = Collections.emptyList();

Expression expression =
        parser.parseExpression("#root.?[#this.startsWith('A')]");

List<?> result =
        expression.getValue(context, names, List.class);
~~~

With an empty collection, selection can return an empty result collection because there are no elements to check. If the root collection is null, SpEL has no collection on which to perform selection and a normal expression can raise an evaluation error.

If null is allowed to be interpreted as an empty collection, normalize it before evaluation:

~~~java
List<String> safeNames =
        names == null ? Collections.emptyList() : names;

List<?> result =
        expression.getValue(context, safeNames, List.class);
~~~

This makes the policy of converting null to an empty collection explicit in Java. If null has a different meaning from empty, do not replace it automatically.

## Root object in Spring integrations

When using SpEL via Spring annotations or modules, the framework usually prepares the EvaluationContext and root object according to the integration context. The root object in a cache, security, or bean configuration expression is not necessarily the same as the root object of a standalone evaluation created manually by the application.

Therefore, do not assume **#root** is always the bean being configured or a specific business object. Consult the documentation of the corresponding integration to see which root object, variables, and properties are provided.

When evaluating expressions manually, the application can control the root object explicitly via StandardEvaluationContext or by passing it to getValue. When using annotations, write expressions based on the data that the integration actually exposes.

## Errors when accessing a null root object

Distinguish syntax errors from evaluation errors:

- **ParseException:** the SpEL string has invalid syntax, such as a missing bracket or an invalid operator.
- **EvaluationException:** the expression is syntactically valid but cannot be executed on the current root object or context, such as reading a property on a null root or calling a method on a null value.

Handling example:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("name");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    String name =
            expression.getValue(context, rootObject, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate expression for the supplied root object", ex);
}
~~~

If a null root is a valid state, handle it using null-safe navigation, Elvis, the ternary operator, or data normalization before evaluation. If root is required, validate early and return a clear input error.

Do not catch every EvaluationException and broadly return null. Doing so can hide misspelled properties, method errors, incompatible data types, or other issues unrelated to a null root.

## Practical rules

- Identify where the root object is supplied: in EvaluationContext or on each getValue call.
- Distinguish a null root from a null property, null collection, and empty collection.
- Use **#root** when you need to reference the base object explicitly.
- Use **?.** at every step that can be null in an access chain.
- Use **?:** or the ternary operator when there is a fallback value valid for the business domain.
- If root is required data, validate in Java before evaluating.
- Do not share a mutable context containing per-request root or variables across threads if that could mix data.
- Handle evaluation errors at an appropriate boundary and retain enough information for diagnostics.

## Conclusion

A null root object does not prevent SpEL from evaluating every kind of expression. Literals and variables can still work, but reading properties or calling methods directly on a null root will fail. **#root** allows checking the base object; **?.** guards null-safe access; **?:** and the ternary operator provide fallback values or explicit handling branches.

Decide whether null is valid according to business rules. If the data is required, validate in Java before evaluating. If null is a normal state, use null-safe navigation and intentional default values. With nested object graphs, guarding every potentially null step and distinguishing a null root from a null property will make expressions easier to predict, diagnose, and maintain.
