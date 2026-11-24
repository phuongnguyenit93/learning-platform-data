# Distinguishing SpEL Variables from Root Object Properties

## Objectives

After this lesson, you can distinguish variables registered in EvaluationContext from properties of the root object in Spring Expression Language (SpEL); write proper syntax with and without the hash prefix; set the root object and variables from Java; handle cases where variable names match property names; and properly use #root and #this in nested expressions. You will also learn how to avoid errors caused by missing variables, a null root object, or namespace confusion.

## 1. Two Data Sources in a SpEL Expression

A SpEL expression often needs to read data from two sources:

- **Root object:** the object supplied as the base target when evaluating the expression. Its properties are usually accessed directly by property name.
- **EvaluationContext variables:** values registered into the context by the application. Variables are referenced with the # prefix.

Examples:

~~~text
name
#name
~~~

These two expressions are not equivalent:

- `name` tells SpEL to read the property named name from the current object, which at the outermost level is usually the root object.
- `#name` tells SpEL to read the variable named name registered in EvaluationContext.

Using the same name does not merge the two data sources into one. The # prefix signals the parser to look up a variable in the context; without the prefix, SpEL performs property access on the current object.

## 2. Accessing Properties of the Root Object

The root object serves as the starting point for evaluating an expression. For example, an application passes a Customer object into SpEL:

~~~java
Customer customer = new Customer();
customer.setName("An");
customer.setAge(28);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(customer, String.class);
~~~

In this example, customer is the root object. The expression `name` reads the name property of that object and returns "An".

Multiple property levels can be read:

~~~text
address.city
customer.profile.displayName
~~~

Each property name is resolved on the current object at the corresponding step. Intermediate objects must exist and properties must be accessible via EvaluationContext's PropertyAccessor.

If the root object is an Order with a customer property, the expression `customer.name` reads customer from the root and then reads name from the child Customer object.

## 3. Referencing Variables with the # Prefix

Variables are registered in EvaluationContext by the application and referenced using the # symbol:

~~~text
#minimumAge
#currentUser
#allowedStatuses
~~~

Java example:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimumAge", 18);
context.setVariable("currentUser", currentUser);
context.setVariable(
    "allowedStatuses",
    List.of("PAID", "SHIPPED")
);
~~~

Then the expression can use the variables:

~~~text
#minimumAge
#currentUser.name
#allowedStatuses
~~~

Variables can hold numbers, strings, booleans, business objects, arrays, or collections. SpEL reads the values supplied by the application; it does not automatically create variables merely because a variable name appears in the expression.

Passing data through variables keeps the expression string stable while input data varies across evaluations. Register values in Java instead of concatenating input data directly into the SpEL string.

## 4. Setting Root Object and Variables in the Same Context

You can provide the root object right when creating StandardEvaluationContext:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.setVariable("requiredCity", "Da Nang");

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "age >= #minimumAge and address.city == #requiredCity"
);

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

In the expression:

- `age` and `address.city` are read from the root object customer.
- `#minimumAge` and `#requiredCity` are read from EvaluationContext.

This approach separates the primary data being evaluated from configuration parameters or thresholds. The root object supplies the state of the object under evaluation; variables supply auxiliary values the expression needs.

You can also set the root object after creating the context:

~~~java
context.setRootObject(customer);
~~~

If you want to provide a dedicated root object for a single evaluation, you can pass it through a getValue overload:

~~~java
Boolean eligible =
    expression.getValue(context, customer, Boolean.class);
~~~

Choose a setup pattern consistent with your application's context lifecycle. Avoid changing the root object between evaluations unintentionally, as the same expression would then read different objects.

## 5. Comparing Root Property and Variable Syntax

The table below summarizes how the two types of references are resolved:

| Syntax | Lookup Source | Example |
|---|---|---|
| `name` | Property of the current object | `name` |
| `address.city` | Nested property on the current object | `address.city` |
| `#name` | Variable in EvaluationContext | `#name` |
| `#customer.name` | Property of the object stored in variable customer | `#customer.name` |
| `#root.name` | Property name of the root object | `#root.name` |
| `#this.name` | Property name of the object that is currently the evaluation object | `#this.name` |

For example, if the root object is Customer, `name` and `#root.name` usually read the same property. However, `#name` reads the variable named name in the context; that variable may hold a completely different value.

Adding or removing the # symbol can change which data source is read, so write the syntax deliberately instead of relying on identical variable or property names.

## 6. When Variables and Properties Share the Same Name

An application can have a name property on the root object and simultaneously register a variable named name:

~~~java
Customer customer = new Customer();
customer.setName("An");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("name", "Binh");
~~~

The following three expressions have different meanings:

~~~text
name
#name
#root.name
~~~

Results:

- `name` reads the root object's property and returns "An".
- `#name` reads the variable and returns "Binh".
- `#root.name` explicitly reads the root object's name property and returns "An".

This is a transparent way to resolve name collisions. When an expression is long or involves multiple objects, using `#root.property` helps readers clearly see that the data comes from the root object.

Name variables according to their role, such as `#minimumTotal`, `#currentUser`, or `#featureEnabled`, to reduce the chance of colliding with data model properties.

## 7. How Do #root and #this Differ?

SpEL provides two special references:

- `#root` always points to the root object of the evaluation.
- `#this` points to the current evaluation object. At the outermost level, #this is usually the root object itself; inside nested expressions such as selection and projection, it can change to the element being processed.

Example at the outermost level:

~~~text
#root.name
#this.name
name
~~~

Without a nested context that changes the evaluation object, all three can read the same property of root.

In selection:

~~~text
#orders.?[total >= #root.minimumTotal]
~~~

Here, `total` is read from the current order, while `#root.minimumTotal` reads the threshold from the original root object.

In projection:

~~~text
#orders.![#this.id]
~~~

`#this` is each order being projected. `#root` remains the original root object of the evaluation.

Distinguishing these two references is especially important in collection operations, because an unprefixed property name inside selection/projection is normally resolved on the current element rather than the original root object.

## 8. Using Variables Holding Objects Instead of a Root Object

Not every object needs to be set as root. You can pass multiple objects via variables:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customer", customer);
context.setVariable("order", order);
context.setVariable("policy", policy);
~~~

Expression:

~~~text
#customer.name
#order.total
#policy.maximumDiscount
~~~

This is useful when a rule needs to combine multiple independent objects. Each variable has its own name, making the data source easy to identify.

Compare:

~~~text
customer.name
~~~

with:

~~~text
#customer.name
~~~

The first expression looks for a customer property on the root object and then reads name. The second looks for the customer variable in the context and then reads name on the object stored in that variable.

If the root object itself is Customer, the expression `customer.name` is only valid when Customer has a property named customer. It does not automatically mean the customer variable.

## 9. Variables in Selection and Projection

Variables registered in EvaluationContext can be used inside selection and projection.

Example of filtering orders whose total meets a threshold:

~~~text
#orders.?[total >= #minimumTotal]
~~~

In the condition expression:

- `total` is a property of the current order.
- `#minimumTotal` is a variable supplied from the context.

Retrieving the IDs of orders meeting the threshold:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

If you need to access a root object property inside a nested condition:

~~~text
#orders.?[total >= #root.minimumTotal]
~~~

Here #root still references the original root object, even while #this represents an order.

Example using all three sources:

~~~text
#orders.?[
    total >= #minimumTotal and
    customerId == #root.customer.id
].![id]
~~~

The condition combines a property of the current element, a context variable, and a property of the root object. When nested expressions become hard to read, put needed data into clearly named variables or move multi-step rules to Java.

## 10. Null Values and Unregistered Variables

A variable can be registered with a null value. A variable reference without a useful value must be handled explicitly:

~~~text
#optionalNote == null
#currentUser != null
~~~

Do not assume every variable mentioned in an expression has already been registered. If a required variable has not been supplied, the expression may receive null or fail at a subsequent access step, depending on usage.

Example:

~~~text
#currentUser.name
~~~

If `#currentUser` is null, reading name on a null value may cause an error. You can use safe navigation:

~~~text
#currentUser?.name
~~~

Or provide a default:

~~~text
#currentUser?.name ?: 'Guest'
~~~

The root object can also be null. If an expression reads a property directly such as `name` when the root object is null, the access cannot succeed. Validate input data before evaluating or use an appropriate guard condition.

If a variable is required by business logic, validate its presence and type in Java before calling getValue. This helps distinguish missing data from a valid null value.

## 11. Registering, Reading, and Updating Variables from Java

EvaluationContext provides an API for the application to manage variables:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimum", 100);
context.setVariable("enabled", true);

Object minimum = context.lookupVariable("minimum");

context.setVariable("minimum", 150);
~~~

`setVariable(...)` registers or replaces a variable's value. `lookupVariable(...)` allows Java to read back the registered value.

After updating a variable, the same Expression can be re-evaluated with the new data:

~~~java
Expression expression =
    parser.parseExpression("#amount >= #minimum");

context.setVariable("amount", 120);
context.setVariable("minimum", 100);

Boolean first = expression.getValue(context, Boolean.class);

context.setVariable("minimum", 150);

Boolean second = expression.getValue(context, Boolean.class);
~~~

The first evaluation returns true; the second returns false because the threshold changed.

Update variables before each evaluation according to the corresponding input data. If multiple threads share a mutable context, root and variable values can interfere with each other. Consider creating a separate context per processing pass or per thread when isolation is needed.

## 12. Variables Are Not Bean References

SpEL uses different prefixes for different namespaces:

| Syntax | Meaning |
|---|---|
| `#orderService` | Variable named orderService in EvaluationContext |
| `@orderService` | Bean named orderService looked up via BeanResolver |
| `orderService` | Property orderService of the current object |

For example, registering a variable from Java:

~~~java
context.setVariable("orderService", serviceMock);
~~~

The expression `#orderService` reads serviceMock. The expression `@orderService` asks BeanResolver to find the bean in the Spring container. These two can return two different objects even with the same name.

If you create StandardEvaluationContext manually and want to use bean references, you must configure a BeanResolver. Registering a variable with setVariable does not create a bean reference and does not require a BeanResolver.

Without the # or @ prefix, SpEL treats the name according to property access rules on the current evaluation object.

## 13. Variables and Properties in SimpleEvaluationContext

SimpleEvaluationContext is a restricted context, configured according to property and method access needs. It can still receive data through variables registered by the application via the API:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumAge", 18);
~~~

The expression can read the variable:

~~~text
age >= #minimumAge
~~~

Here age is read from the current root object, while #minimumAge is read from the variable in the context.

Property access capability depends on the configured PropertyAccessor. SimpleEvaluationContext does not provide all features of StandardEvaluationContext, so do not assume every method, type reference, bean reference, or constructor invocation is supported.

If an expression only needs to read a few properties and compare them against passed parameters, a restricted context can be suitable. Explicitly configure the needed permissions and test with the exact context type the application uses at runtime.

## 14. Common Mistakes When Confusing Variables and Root Properties

Common mistakes include:

- **Forgetting the # symbol:** writing `minimumAge` when minimumAge was only registered as a variable.
- **Adding # in the wrong place:** writing `#name` when name is a property of the root object and no corresponding variable exists.
- **Wrong root object type:** the expression accesses a property that does not exist on the passed-in object.
- **Name collisions:** variable and property share the same name, but the author does not specify which source to read.
- **Confusing beans with variables:** using `#service` when only the bean `@service` is registered.
- **Null root object:** accessing properties directly when there is no root object.
- **Null variable:** reading a subsequent property on a null object.
- **Confusing #this with #root:** inside selection/projection, #this has switched to the current element while the expression actually needs a root object property.

When debugging, identify which namespace each name in the expression belongs to: evaluation object property, context variable, or bean looked up by resolver. Then inspect the actual object, data type, and values registered from Java.

## 15. Comprehensive Example

Suppose an application needs to evaluate an order based on a root object, a threshold variable, and an allowed-statuses variable:

~~~java
Order order = loadOrder();

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("allowedStatus", List.of("PAID", "SHIPPED"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "total >= #minimumTotal and #allowedStatus.contains(status)"
);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

In the expression:

- `total` and `status` are properties of the root object Order.
- `#minimumTotal` is a variable holding the monetary threshold.
- `#allowedStatus` is a variable holding the list of allowed statuses.

You can explicitly indicate the property source using #root:

~~~text
#root.total >= #minimumTotal
and #allowedStatus.contains(#root.status)
~~~

Both ways express the same meaning when the evaluation object at the outermost level is the root object. The explicit style can be helpful when the expression has multiple nesting levels.

## 16. Testing Expression Namespaces

When testing, create cases that clearly distinguish root properties from variables:

| Case | Data | What to Verify |
|---|---|---|
| Root property | Root has name = "An" | `name` reads "An" |
| Variable | Context has name = "Binh" | `#name` reads "Binh" |
| Same name | Root name = "An", variable name = "Binh" | Both syntaxes return two different values |
| Explicit root reference | Root has name = "An" | `#root.name` reads "An" |
| Current object | Evaluated at outermost level | `#this` points to root |
| Nested collection | Selection on a list | `#this` is the current element |
| Null root | No root object | Property access is handled properly |
| Null variable | Variable has null value | Safe navigation or null condition works |
| Missing variable | Required variable not registered | Validation detects missing input data |
| Bean with same name | Both bean and variable share a name | `@name` differs from `#name` |

Testing both normal cases and colliding-name cases helps avoid bugs from reading the wrong data when expressions are edited or the context changes.

## 17. Key Takeaways

Properties without the # prefix are read from the current evaluation object; at the outermost level, that is usually the root object. Variables registered in EvaluationContext must be referenced with #, such as #minimumAge or #currentUser.name.

You can set the root object via the context constructor, setRootObject, or a getValue overload accepting a root object. Use setVariable to supply auxiliary data. When a variable and a property share the same name, name reads the property whereas #name reads the variable; #root.name explicitly specifies the root's property.

#root always references the original root object. #this references the current evaluation object and can change during selection/projection. Inside nested expressions, use #root when root data is needed and #this or unprefixed properties when the current element is needed.

Bean reference @name is a separate namespace, unlike variable #name. Validate the root object and required variables, handle null intentionally, and create a context matching the access permissions the expression needs.

## References

- [Spring Framework Reference — Variables](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Evaluation Context](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)