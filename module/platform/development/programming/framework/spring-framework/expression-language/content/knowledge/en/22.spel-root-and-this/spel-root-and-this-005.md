# Root Object with Property and Method Resolution

In Spring Expression Language (SpEL), expressions are typically evaluated within an EvaluationContext. The context provides the root object, variables, property accessors, method resolvers, type locators, and other services required to interpret the expression.

The root object is the default object an expression accesses when no variable name is specified. For example, if the root object is an Order, the expression **status** can read Order's status property and **calculateTotal()** can invoke the corresponding method on Order.

SpEL distinguishes between **#root** and **#this**. **#root** always references the root object of the evaluation pass; **#this** is the current object at the position being evaluated and can change in operations such as selection or projection. Understanding these two variables properly helps write clear expressions, especially when there are multiple nested objects.

## 1. What is the root object?

### 1.1. The default object of an expression

The root object is the object that SpEL uses as its starting point when resolving a property or method without an explicitly written receiver.

Example Order class:

~~~java
public class Order {

    private final String id;
    private final String status;
    private final BigDecimal total;

    public Order(String id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public boolean isPaid() {
        return "PAID".equals(status);
    }

    public BigDecimal calculateTotal() {
        return total;
    }
}
~~~

Create parser and context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(
        "O-100",
        "PAID",
        new BigDecimal("125.50")
);

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
~~~

Evaluate properties and methods on the root object:

~~~java
String id = parser
        .parseExpression("id")
        .getValue(context, String.class);

Boolean paid = parser
        .parseExpression("isPaid()")
        .getValue(context, Boolean.class);
~~~

Here, **id** and **isPaid()** are resolved on Order because Order is the context's root object.

### 1.2. Setting the root object after creating the context

You can create the context first and then set the root object:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(order);
~~~

Or create the context with the root object right from the start:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);
~~~

Both ways set Order as the root object. If the context is reused, pay attention to changing the root object between evaluation calls so you do not accidentally evaluate expressions on another request's data.

### 1.3. The root object can be a DTO or view object

The root object does not have to be an entity or service. You can use a small DTO containing only the data the expression needs:

~~~java
public record OrderExpressionView(
        String status,
        BigDecimal total,
        boolean customerActive
) {
}
~~~

Create context:

~~~java
OrderExpressionView view =
        new OrderExpressionView("PAID", new BigDecimal("125.50"), true);

StandardEvaluationContext context =
        new StandardEvaluationContext(view);
~~~

Expression:

~~~java
status == 'PAID' && customerActive && total > 100
~~~

A compact root object makes expressions easier to understand and limits accidental access to other parts of the domain model.

## 2. #root and #this

### 2.1. #root references the root object

The special variable **#root** always references the root object supplied to EvaluationContext:

~~~java
#root.status
#root.total
#root.isPaid()
~~~

When an expression is evaluated directly on the root object Order, **status** and **#root.status** usually produce the same result.

Writing **#root** explicitly is useful when an expression has multiple access levels or when the context is evaluating a current object that differs from the root object.

### 2.2. #this is the current object

The **#this** variable represents the current object at the evaluation position. At the outermost level, it is usually the root object. In operations such as selection and projection, **#this** changes with the element being processed.

Example:

~~~java
#this.status
~~~

Outside selection, if the root object is Order, the expression reads Order's status.

Inside selection:

~~~java
orders.?[#this.total > 100]
~~~

Here, **#this** is each order being examined, while **#root** remains the root object containing the orders property.

### 2.3. Comparing #root and #this in collections

Suppose the root object is Report:

~~~java
public class Report {

    private final String currentCustomerId;
    private final List<Order> orders;

    public Report(String currentCustomerId, List<Order> orders) {
        this.currentCustomerId = currentCustomerId;
        this.orders = orders;
    }

    public String getCurrentCustomerId() {
        return currentCustomerId;
    }

    public List<Order> getOrders() {
        return orders;
    }
}
~~~

Expression:

~~~java
orders.?[
    #this.customerId == #root.currentCustomerId
]
~~~

Inside the predicate:

- **#this** is the current Order in the list.
- **#root** is Report.
- **#this.customerId** reads the customer ID of the order.
- **#root.currentCustomerId** reads the current customer ID from the report.

Do not replace **#root** with **#this** in this example, because when selection runs, #this has already switched to the Order element.

### 2.4. #this changes in projection

Projection uses the **.![]** operator to transform each element. In projection, #this is the current element:

~~~java
orders.![#this.id]
~~~

The result is a list of the orders' IDs.

The root object can be used in the transformation:

~~~java
orders.![#this.total + #root.adjustment]
~~~

This example computes a value for each order based on the current element's total and the root object's adjustment.

When nesting selection/projection, identify the current object at the exact position of the predicate or projection instead of assuming #this is always the root object.

## 3. Property access on the root object

### 3.1. Property notation

SpEL allows accessing properties by property name:

~~~java
status
total
customer.name
~~~

In a standard Java bean, property notation is usually resolved via the corresponding getter, such as **getStatus()**, **getTotal()**, or **isActive()**. Depending on the configured PropertyAccessor, SpEL can also access other data structures.

Property notation **status** differs from an explicit method call **getStatus()**:

- **status** requests access to the status property.
- **getStatus()** requests invoking the method named getStatus.

Use property notation when expressing data, and method calls when performing a clearly named behavior.

### 3.2. Nested property access

Multiple properties can be chained with dots:

~~~java
customer.address.city
~~~

Each step is resolved on the object returned by the previous step. If customer or address is null, subsequent access can cause an evaluation error.

You can check for null using short-circuit conditions:

~~~java
customer != null
    && customer.address != null
    && customer.address.city == 'Hanoi'
~~~

Or use safe navigation where needed if your Spring version supports it:

~~~java
customer?.address?.city
~~~

Safe navigation handles a null receiver at the position where the operator is placed. It does not turn a non-existent property into null, nor does it catch all exceptions.

### 3.3. Properties on Maps and collections

For a Map, values can be accessed by key:

~~~java
settings['theme']
settings['timeout']
~~~

Indexer syntax is usually clearer when the key is a string or contains characters unsuitable for property notation.

For a List or array, use indices:

~~~java
items[0]
scores[2]
~~~

Indices are zero-based. If an index is out of bounds, evaluation may fail.

### 3.4. Read-only and writable properties

When an expression only reads, SpEL needs a PropertyAccessor that can read the property. If using **setValue**, the accessor must also support writing and the property must be mutable:

~~~java
parser.parseExpression("status")
        .setValue(context, "SHIPPED");
~~~

This example only succeeds if the root object has a status property that is writable according to the accessor in use. A record or immutable object typically has no setter to perform updates.

Do not assume every readable property is writable. Check the contract of both the object and the PropertyAccessor.

## 4. PropertyAccessor and the property resolution mechanism

### 4.1. What does PropertyAccessor do?

PropertyAccessor is an extension point that lets SpEL read or write properties of an object. An accessor can support one or multiple types of target objects.

StandardEvaluationContext includes a reflective accessor for Java objects by default. It typically reads JavaBean properties via getters and supports field access according to Spring's rules.

When an expression reads:

~~~java
customer.name
~~~

SpEL finds a PropertyAccessor that can handle the customer object and the name property. If the accessor can read it, it returns the property value for the rest of the expression.

### 4.2. Adding a custom PropertyAccessor

An application can add an accessor for a specialized data type:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.addPropertyAccessor(new CustomPropertyAccessor());
~~~

CustomPropertyAccessor needs to implement the PropertyAccessor methods, including identifying supported target classes, checking read/write capability, and performing the corresponding operation.

Add an accessor only when there is a specific data model to support. An overly broad accessor can alter how properties are resolved across many object types and make expressions hard to predict.

### 4.3. Accessor order and scope

When multiple accessors exist, target support and registration order can affect which accessor is used. If a custom accessor handles a specific object type, restrict **getSpecificTargetClasses()** appropriately instead of claiming support for all objects.

If an accessor reads properties but does not write them, return accurate answers for **canRead** and **canWrite**. Do not declare writable and then throw an error at the write step if the data type is inherently immutable.

## 5. Method resolution on the root object

### 5.1. Calling methods directly

Methods on the root object can be called by name and argument list:

~~~java
calculateTotal()
isPaid()
hasItem('P-100')
~~~

Example:

~~~java
BigDecimal total = parser
        .parseExpression("calculateTotal()")
        .getValue(context, BigDecimal.class);
~~~

SpEL finds the method on the target object using MethodResolver. With StandardEvaluationContext, the default resolver uses reflection to locate a matching method.

### 5.2. Methods with arguments

Arguments can be literals, properties, variables, or other expressions:

~~~java
hasItem('P-100')
hasItem(#productCode)
calculateDiscount(total, #customerTier)
~~~

Arguments are evaluated before the method is invoked. If an argument type does not match the method signature, TypeConverter may be used to convert it when the configuration supports doing so.

A non-existent, inaccessible, or unmatched-overload method will cause an error during evaluation, even though the expression may parse successfully.

### 5.3. Distinguishing properties and methods

Compare:

~~~java
active
isActive()
~~~

**active** is a property access. In a Java bean, it is usually read through the **isActive()** getter.

**isActive()** is an explicit method call. Both forms can retrieve the same information, but their semantics at the SpEL level differ.

When writing expressions, prefer property notation for state data. Use method calls for behaviors or computations with appropriate names.

### 5.4. Overloading and argument conversion

A class can have multiple methods with the same name:

~~~java
public String format(String value) {
    return "text:" + value;
}

public String format(Long value) {
    return "number:" + value;
}
~~~

SpEL must resolve the appropriate method based on name, argument count, and type compatibility. If multiple overloads can accept the arguments after conversion, the choice may depend on the resolver and TypeConverter.

To avoid ambiguity:

- Keep the number of overloads moderate.
- Use distinct method names for different behaviors.
- Pass data with explicit types when a specific overload must be selected.
- Test expressions with the actual Spring configuration.
- Do not rely on method declaration order in source code to infer which overload is selected.

## 6. MethodResolver and MethodExecutor

### 6.1. MethodResolver

MethodResolver finds a method matching the method name and argument list on the target object. The interface receives the EvaluationContext, target object, method name, and argument types, then returns an appropriate MethodExecutor.

StandardEvaluationContext uses ReflectiveMethodResolver by default. Applications can add custom MethodResolvers when a different method-invocation policy is needed.

### 6.2. MethodExecutor

After the resolver locates a matching method, MethodExecutor executes the invocation with the prepared target and arguments.

Separating these two steps helps distinguish:

- No matching method found: a resolution issue.
- Method found but invocation failed: possibly an argument conversion issue, access permission issue, or logic inside the method.

### 6.3. Registering a custom resolver

A resolver can be added:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.addMethodResolver(new CustomMethodResolver());
~~~

A custom resolver should strictly restrict allowed target classes, method names, and signatures. Do not create a resolver that allows calling any method just to handle one special case.

If you only need to provide a few behaviors to an expression, it is usually easier to control by creating a facade with clear public methods and placing the facade in the context as a variable.

## 7. Root object, variables, and bean references

These three common ways of accessing objects serve different purposes:

| Access mechanism | Syntax | Object source |
|---|---|---|
| Root object | **status**, **#root.status** | Root object of EvaluationContext |
| Context variable | **#order.status** | Variable registered via setVariable |
| Bean reference | **@pricingService.quote(...)** | BeanResolver of EvaluationContext |

Registering a variable:

~~~java
context.setVariable("order", order);
~~~

Accessing the variable:

~~~java
#order.status
~~~

Bean references only work when the context has an appropriate BeanResolver:

~~~java
@pricingService.quote('P-100')
~~~

Do not confuse context variables with bean references. Variables are assigned directly to the context; bean references require a resolver to look up beans by name.

For untrusted expressions, do not grant a broad bean resolver or a root object holding excessive permissions. Provide only the objects and methods truly required.

## 8. Example combining root, variables, and methods

Suppose the root object is Order, and the context has the variable customerTier:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("customerTier", "GOLD");
context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

Expression:

~~~java
#root.status == 'PAID'
    && total >= #minimumTotal
    && supportsTier(#customerTier)
~~~

Where:

- **#root.status** accesses the property on the root object.
- **total** also accesses a property of the root object.
- **#minimumTotal** and **#customerTier** are context variables.
- **supportsTier(...)** calls a method on the root object.

This style separates data belonging to Order from external parameters supplied via the context.

If an expression grows longer, group parts with parentheses or move a named rule into its own method so readers can understand it easily.

## 9. Handling null and resolution errors

### 9.1. Null root object

Some expressions using only literals or variables may not need a root object. However, if an expression accesses a property or calls a method on a null root object, evaluation can fail.

Validate the root object before evaluating:

~~~java
if (order == null) {
    throw new IllegalArgumentException("Order is required");
}

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
~~~

Do not use a dummy root object or default value if doing so changes business semantics.

### 9.2. Non-existent property

If an expression references a property not supported by an accessor, SpEL may throw an evaluation error. Check the property name, getter, target class, and registered accessors.

A non-existent property error differs from a property that exists with a null value. Safe navigation only handles a null receiver; it does not fix an incorrect property name.

### 9.3. Missing or incompatible method

If no matching method is found, check:

- Method name and letter case.
- Number of arguments.
- Actual argument types.
- Existing overloads.
- Conversion capability of TypeConverter.
- Configured MethodResolver.
- Runtime method accessibility.

Do not catch all resolution errors and return null. Doing so can mask configuration or programming mistakes.

### 9.4. Distinguishing parse and evaluate

Parsing checks syntax and creates an Expression. Property resolution and method invocation typically occur during evaluation.

Therefore:

- Syntax-invalid expressions throw ParseException.
- Inaccessible properties or unmatched methods typically throw EvaluationException or a specific subtype.
- A method may be found yet throw an exception during execution.
- Argument conversion can fail when the call is evaluated.

Catch and classify exceptions at the right boundary, preserving the cause for investigation.

## 10. Designing a safe and controllable context

### 10.1. Provide only necessary objects

A root object can expose an entire object graph. If an expression only needs status and total, there is no need to pass a service or large entity with many relationships.

Using a small DTO/view helps limit the properties an expression can read and reduces the risk of calling unintended methods.

### 10.2. Consider SimpleEvaluationContext

If you only need to read properties and do not need full SpEL features, you can use SimpleEvaluationContext with an appropriate configuration:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

SimpleEvaluationContext restricts several capabilities compared to StandardEvaluationContext, such as type references, constructors, and bean references. Method invocation also needs to be intentionally enabled via the builder configuration if the application genuinely needs it.

A restricted context does not replace input validation, resource limits, or authorization in the service layer.

### 10.3. Do not share stateful contexts across requests

EvaluationContext holds a root object, variables, and accessor/resolver configuration. If variables or the root object are mutated between requests, data can be misused if the context is shared improperly.

Create a context per request or per evaluation pass, or use an immutable configuration designed for safe sharing. Do not store user data in variables of a shared context.

## 11. Testing root object and resolution

Test root properties, method calls, variables, #root, and #this separately:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(
        "O-100",
        "PAID",
        new BigDecimal("125.50")
);

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

assertEquals(
        "O-100",
        parser.parseExpression("id")
                .getValue(context, String.class)
);

assertEquals(
        "O-100",
        parser.parseExpression("#root.id")
                .getValue(context, String.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("isPaid()")
                .getValue(context, Boolean.class)
);
~~~

Testing variables:

~~~java
context.setVariable("minimum", new BigDecimal("100"));

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("total >= #minimum")
                .getValue(context, Boolean.class)
);
~~~

For selection, test that #this is the current element while #root remains the root object:

~~~java
orders.?[
    #this.customerId == #root.currentCustomerId
]
~~~

In addition, test null root, null property, missing property, missing method, overloads, and converter failures. These cases verify resolution at the evaluation stage.

## 12. Summary

The root object is the default starting point of a SpEL expression. PropertyAccessor reads or writes properties; MethodResolver finds matching methods; MethodExecutor executes invocations; TypeConverter assists with argument conversion when needed.

- **#root** always references the root object of EvaluationContext.
- **#this** references the current object and can change in selection/projection.
- Property notation such as **status** is used to read data; method calls such as **calculateTotal()** invoke behavior.
- PropertyAccessor and MethodResolver are extension points to customize access behavior.
- Context variables use the **#name** syntax; bean references use **@beanName** and require a BeanResolver.
- Successful parsing does not guarantee that properties or methods will resolve successfully at evaluation time.

Provide a small root object with a clear contract, limit accessors/resolvers to what is needed, and scope the context to its usage. That makes expressions easier to read, easier to test, and less likely to grant unintended access.