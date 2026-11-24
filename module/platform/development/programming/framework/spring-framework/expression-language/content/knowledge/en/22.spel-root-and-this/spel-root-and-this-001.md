# Root Object in Spring Expression Language (SpEL) StandardEvaluationContext

In Spring Expression Language (SpEL), the **root object** is the base object that an expression uses as its starting point when resolving properties and methods without a variable prefix. `StandardEvaluationContext` stores the root object along with the components needed to evaluate expressions, such as property accessors, method resolvers, variables, functions, and type converters.

When an expression such as `name` is evaluated, SpEL looks up the `name` property on the current root object. If an expression uses `#root`, it explicitly references the root object. Understanding the role of the root object properly helps control input data, reuse expressions, and avoid confusion with the current object `#this`.

## 1. What is the root object?

The root object is the object set as the root context when SpEL evaluates an expression. Properties or methods referenced directly without the `#` prefix are usually resolved from this object.

For example, given the Customer class:

~~~java
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public boolean isAdult() {
        return age >= 18;
    }
}
~~~

Create a Customer and use it as the root object:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

ExpressionParser parser = new SpelExpressionParser();

String name = parser.parseExpression("name")
        .getValue(context, String.class);

Boolean adult = parser.parseExpression("isAdult()")
        .getValue(context, Boolean.class);
~~~

In these two expressions:

- `name` is resolved from the root object `customer`.
- `isAdult()` invokes a method on the root object.
- `getValue(context, ...)` evaluates the expression in the configured context.

The root object is neither the expression string itself nor `ExpressionParser`. It is the data from which the expression begins accessing values.

## 2. Creating StandardEvaluationContext with a root object

`StandardEvaluationContext` belongs to the `org.springframework.expression.spel.support` package. The simplest way to set the root object is to pass the object into the constructor:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);
~~~

The context holds the customer object as the root object for evaluations that use that context.

You can also create the context first and set the root object afterward:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(customer);
~~~

Both approaches set the root object. Using the constructor is suitable when the root object is already available at context creation time. `setRootObject(...)` is useful when you need to change the root object after the context has been created.

You can retrieve the current root object via:

~~~java
TypedValue root = context.getRootObject();
Object value = root.getValue();
~~~

`getRootObject()` returns a `TypedValue`, not the object directly as `Object`. Call `getValue()` on TypedValue to retrieve the wrapped object inside.

## 3. Evaluating expressions using the root object in context

After creating the context, pass the context into `getValue(...)`:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(
                new Customer("Lan", 25)
        );

Expression expression = parser.parseExpression("age >= 18");

Boolean result = expression.getValue(context, Boolean.class);

// result == true
~~~

In the example, the expression does not need to specify a variable name or pass customer directly into each call. SpEL uses the root object stored in the context to resolve `age`.

A single context can be used for multiple expressions:

~~~java
Expression nameExpression = parser.parseExpression("name");
Expression ageExpression = parser.parseExpression("age");
Expression adultExpression = parser.parseExpression("isAdult()");

String name = nameExpression.getValue(context, String.class);
Integer age = ageExpression.getValue(context, Integer.class);
Boolean adult = adultExpression.getValue(context, Boolean.class);
~~~

This approach is useful when a group of expressions works together on the same business object. The parser can parse each string into an Expression; the context provides the shared root object and evaluation environment.

If you want to evaluate the same Expression against different objects, you can replace the root object in the context or pass a separate root object via the appropriate overload of `getValue(...)`.

## 4. Changing the root object with setRootObject

`setRootObject(...)` lets you change the root object of the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression = parser.parseExpression("name");

context.setRootObject(new Customer("Lan", 25));
String firstName = expression.getValue(context, String.class);

context.setRootObject(new Customer("Minh", 31));
String secondName = expression.getValue(context, String.class);
~~~

The same Expression is evaluated twice against two different root objects. The first time the result is Lan; the second time the result is Minh.

This allows reusing expressions when the property structure required by the expression remains compatible across objects. If the new root object does not have the property or method referenced by the expression, evaluation may fail.

When a context is shared across multiple threads or multiple requests, avoid mutating a shared root object in a way that causes evaluations to interfere with each other. In concurrent applications, create a separate context per unit of work or manage context lifecycle explicitly.

## 5. How do #root and #this differ?

SpEL provides two important special variables:

- `#root` always references the root object of the current evaluation.
- `#this` references the object that is the current evaluation context at the point where the expression is being evaluated.

When an expression only accesses the root object directly, `#root` and `#this` usually point to the same object:

~~~text
name
#root.name
#this.name
~~~

Example:

~~~java
Expression expression = parser.parseExpression("#root.name");

String name = expression.getValue(context, String.class);
~~~

In this simple expression, `#root.name` reads the name property of the root object.

The difference becomes clear in nested expressions such as selection and projection. When SpEL iterates over a collection, `#this` becomes the current element, while `#root` still references the original root object.

For example, suppose the root object is CustomerReport with a customers property:

~~~java
public class CustomerReport {
    private final List<Customer> customers;
    private final String region;

    public CustomerReport(List<Customer> customers, String region) {
        this.customers = customers;
        this.region = region;
    }

    public List<Customer> getCustomers() {
        return customers;
    }

    public String getRegion() {
        return region;
    }
}
~~~

Expression:

~~~text
customers.?[#this.age >= 18].![#this.name + ' - ' + #root.region]
~~~

In selection, `#this` is the Customer being checked. In projection, `#this` is the Customer being transformed. `#root.region` still retrieves region from the outer CustomerReport.

Distinguishing these two variables is especially useful when an expression has nested collections or needs to combine data from the root object with data from each element.

## 6. Root object and variables in EvaluationContext

The root object and variables are two different mechanisms for accessing data.

| Syntax | Data source |
|---|---|
| `name` | Property or method resolved from the current root object |
| `#root.name` | The name property of the root object, explicitly referenced |
| `#minimumAge` | The minimumAge variable registered in EvaluationContext |
| `#this.name` | The name property of the current object at the evaluation position |

Registering variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.setVariable("region", "South");

Expression expression = parser.parseExpression(
        "age >= #minimumAge"
);

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

In this expression, `age` comes from the root object, while `#minimumAge` comes from a variable in the context.

Variables can be used together with the root object:

~~~text
#root.age >= #minimumAge and #root.region == #region
~~~

The variable name after `#` is registered using `setVariable(...)`. If a variable has not been registered or its value does not have a compatible type, the expression may not evaluate as expected.

## 7. A root object can be a business domain object

A root object does not have to be a class created specifically for SpEL. It can be any object that has the properties or methods the expression needs to access.

For example, a configuration object can be used:

~~~java
public class FeatureSettings {
    private final boolean checkoutEnabled;
    private final int maximumItems;

    public FeatureSettings(boolean checkoutEnabled, int maximumItems) {
        this.checkoutEnabled = checkoutEnabled;
        this.maximumItems = maximumItems;
    }

    public boolean isCheckoutEnabled() {
        return checkoutEnabled;
    }

    public int getMaximumItems() {
        return maximumItems;
    }
}

FeatureSettings settings = new FeatureSettings(true, 20);

StandardEvaluationContext context =
        new StandardEvaluationContext(settings);

Boolean enabled = parser.parseExpression("checkoutEnabled")
        .getValue(context, Boolean.class);

Integer limit = parser.parseExpression("maximumItems")
        .getValue(context, Integer.class);
~~~

The root object can be a DTO, entity, configuration object, report object, or an object dedicated to supplying data for expressions.

You should expose only the objects and properties that the expression actually needs. This clarifies the input data and reduces unnecessary access surface.

## 8. Root object and property/method resolution

When an expression accesses a property or method on the root object, SpEL uses the components of EvaluationContext to resolve how the access is performed.

`StandardEvaluationContext` supports reflective access mechanisms for ordinary Java objects by default. It can be extended with PropertyAccessor or MethodResolver depending on the use case.

For example, if the root object is Customer:

~~~text
name
age
isAdult()
~~~

SpEL can read properties through a suitable accessor and invoke methods if the method resolver permits.

If a property does not exist, a getter is unsuitable, or a method cannot be resolved, evaluation may throw an error. In that case, check:

- The actual root object set in the context.
- Property and method names in the expression.
- Public getters, setters, or methods of the class.
- Registered PropertyAccessor and MethodResolver instances.
- The result type requested by the Java code.

Do not assume that setting a root object guarantees every property or method is accessible. Accessibility also depends on the object structure and context configuration.

## 9. Root object and getValue(rootObject)

In addition to storing the root object in StandardEvaluationContext, overloads of Expression allow passing the root object directly during evaluation.

Example:

~~~java
Expression expression = parser.parseExpression("name");

Customer customer = new Customer("Lan", 25);

String name = expression.getValue(customer, String.class);
~~~

This approach is suitable when you only need to evaluate an expression against a root object and do not need to configure additional variables, resolvers, or accessors.

When you need to configure multiple components of EvaluationContext, create a StandardEvaluationContext and set the root object on it:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.addPropertyAccessor(new CustomerPropertyAccessor());

Boolean eligible = parser.parseExpression(
        "age >= #minimumAge"
).getValue(context, Boolean.class);
~~~

Do not confuse the `getValue(rootObject, ...)` overload with passing an EvaluationContext. One overload takes the root object directly; another takes a configured context. Choose the overload based on the evaluation environment the expression needs.

## 10. Root object in collections, selection, and projection

In collection expressions, the current object can change as SpEL iterates over each element.

Suppose the root object is CustomerReport with a customers list and a region property. You can filter adult customers and then create strings combining name and region:

~~~text
customers.?[#this.age >= 18].![#this.name + ' - ' + #root.region]
~~~

Evaluation steps:

1. The initial root object is CustomerReport.
2. `customers` retrieves the collection from the root object.
3. During selection, `#this` is the current Customer.
4. Customers with age 18 or above are retained.
5. During projection, `#this.name` retrieves each Customer's name.
6. `#root.region` retrieves region from the root CustomerReport.

If you mistakenly use `#this.region` in projection, SpEL will look for region on the current Customer. The result may be wrong or throw an error if Customer does not have that property.

When writing nested expressions, use `#root` for data belonging to the root object and `#this` for the element being processed.

## 11. Root object and SimpleEvaluationContext

`StandardEvaluationContext` provides broad evaluation capabilities, including property access, method invocation, variables, functions, and configurable resolvers.

In cases where features need to be restricted, Spring provides `SimpleEvaluationContext`. This context lets you choose the scope of property access and method invocation capabilities suitable for data binding needs.

Example using SimpleEvaluationContext with a property accessor:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

String name = parser.parseExpression("name")
        .getValue(context, customer, String.class);
~~~

In the example, the root object is passed directly for the evaluation. SimpleEvaluationContext can also be created with specific property accessors via the corresponding builder.

Choose StandardEvaluationContext when full evaluation capabilities are needed. Choose SimpleEvaluationContext when functionality can be restricted and you want clearer control over which operations expressions are allowed to perform.

## 12. Common mistakes

| Error | Cause | How to fix |
|---|---|---|
| Expression cannot find property | The root object has not been set or does not have the corresponding property. | Check the constructor/setRootObject and the property name. |
| Confusing #root with #this | In selection/projection, #this is the current element. | Use #root for the root object and #this for the element being iterated. |
| Registering a variable but forgetting # | Variables in SpEL are referenced with the #variable syntax. | Use the exact variable name with the # prefix. |
| Expression fails after changing the root object | The new object lacks a property/method required by the expression. | Ensure the root objects have compatible structures. |
| Treating getRootObject() as returning Object | The method returns TypedValue. | Call getValue() on the TypedValue. |
| Using a shared context and changing root object across threads | Evaluations may observe unexpected root object changes. | Create a separate context per thread or unit of work. |
| Assuming root object opens all access permissions | Accessors and resolvers still decide which properties/methods are supported. | Check the EvaluationContext configuration. |
| Using StandardEvaluationContext for untrusted expressions | The context can expose powerful access capabilities. | Limit the root object and consider SimpleEvaluationContext. |

## 13. Takeaways

- The root object is the base object SpEL uses to resolve properties and methods without a variable prefix.
- You can set the root object via the StandardEvaluationContext(rootObject) constructor or setRootObject(...).
- getRootObject() returns TypedValue; call getValue() to get the wrapped object inside.
- `#root` always references the root object; `#this` references the current object and can change during selection/projection.
- Variables are registered with setVariable(...) and referenced via the #variable syntax.
- An Expression can be evaluated on different root objects as long as they satisfy the structure required by the expression.
- You can pass the root object directly to getValue(...) or store it in EvaluationContext.
- PropertyAccessor and MethodResolver still determine how properties and methods are accessed.
- Choose StandardEvaluationContext or SimpleEvaluationContext according to the required feature scope.
