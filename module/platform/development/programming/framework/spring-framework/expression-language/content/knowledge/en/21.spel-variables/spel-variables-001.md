# Declaring and Reading Variables in EvaluationContext

In Spring Expression Language (SpEL), a **variable** is a value supplied by the application to the expression evaluation environment. Variables allow an expression to use externally prepared data without hardcoding values in the SpEL string or putting all data into the root object.

In an expression, a variable is referenced using the **#** symbol followed by the variable name, for example **#minimumPrice**, **#customer**, or **#requestId**. The application declares variables on **EvaluationContext**, typically using the **setVariable(...)** method of StandardEvaluationContext.

A variable can hold numbers, strings, Booleans, collections, or a Java object. Once provided, the expression can read the value itself, access properties, call methods if the context allows, or combine it with SpEL operators.

## Declaring Variables with setVariable(...)

A simple example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumAge", 18);

Expression expression =
        parser.parseExpression("#minimumAge >= 18");

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

The **setVariable("minimumAge", 18)** method registers a variable named minimumAge with the Integer value 18 in the context. In the SpEL string, **#minimumAge** reads that value. The result of the comparison is true.

The name passed to setVariable does not need the # symbol. The # symbol only appears when referencing the variable inside the expression. Variable names are case-sensitive; the exact same casing must be used when declaring and when reading.

You can update a variable's value in the context:

~~~java
context.setVariable("minimumAge", 21);

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

The same Expression can be re-evaluated and receive the new value from the context. This is useful when the expression syntax is fixed while the input data changes on each execution.

## Reading Variables with #variable

The variable reference syntax is **#variableName**:

~~~java
context.setVariable("greeting", "Hello");
context.setVariable("name", "An");

Expression expression =
        parser.parseExpression("#greeting + ' ' + #name");

String message =
        expression.getValue(context, String.class);
~~~

The result is **Hello An**. Both variables are retrieved from EvaluationContext and concatenated with the string literal in the expression.

Variables can also be used in calculations:

~~~java
context.setVariable("unitPrice", new BigDecimal("12.50"));
context.setVariable("quantity", 4);

Expression expression =
        parser.parseExpression("#unitPrice * #quantity");

BigDecimal total =
        expression.getValue(context, BigDecimal.class);
~~~

In this example, both operands come from variables. SpEL evaluates the multiplication and returns the numeric result of the corresponding type. When an expression handles currency or decimal numbers requiring precision, BigDecimal should be provided right from the input instead of passing Double.

## Distinguishing Variables from Root Object Properties

The root object is the object set as the root target for the evaluation. Properties of the root object can be accessed directly by property name. Variables in the context are referenced with the # symbol.

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

~~~java
Product product =
        new Product("Keyboard", new BigDecimal("80.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(product);

context.setVariable(
        "minimumPrice",
        new BigDecimal("50.00"));

Expression expression =
        parser.parseExpression("price >= #minimumPrice");

Boolean eligible =
        expression.getValue(context, Boolean.class);
~~~

In the expression:

- **price** is a property of the root object product.
- **#minimumPrice** is a variable supplied by the application to EvaluationContext.
- The result is true because the product price is greater than or equal to the threshold.

You can explicitly write the root object using **#root.price**:

~~~text
#root.price >= #minimumPrice
~~~

This explicit syntax is helpful when an expression involves multiple objects or when inside collection selection/projection where #this changes to the current element.

## Variables Can Hold Objects

A variable does not only store primitive values or strings. It can reference a Java object, after which the expression accesses properties of that object:

~~~java
Customer customer =
        new Customer("An", "an@example.com");

context.setVariable("customer", customer);

Expression expression =
        parser.parseExpression("#customer.email");

String email =
        expression.getValue(context, String.class);
~~~

Here, **#customer** is a variable holding a reference to the Customer object. **#customer.email** reads the email property of that object through the property access mechanism in EvaluationContext.

If the context allows calling instance methods, the expression can also invoke a method on the object:

~~~java
Expression expression =
        parser.parseExpression("#customer.getEmail()");
~~~

Method invocation capability depends on the method resolver and context configuration. With SimpleEvaluationContext created using the read-only data binding builder, instance method invocation is not enabled by default. You should not grant method invocation permissions if the use case only needs property reading.

## Variables Can Hold Collections or Maps

An application can put a collection into the context and then use that variable in SpEL collection operations:

~~~java
List<Integer> scores = List.of(65, 82, 91, 74);

context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores.?[#this >= 80]");

List<?> passed =
        expression.getValue(context, List.class);
~~~

The result contains 82 and 91. In the selection predicate, **#scores** references the declared collection; **#this** is the current element being checked.

With a Map, the variable can also be accessed by key:

~~~java
Map<String, String> settings = Map.of(
        "theme", "dark",
        "language", "vi");

context.setVariable("settings", settings);

Expression expression =
        parser.parseExpression("#settings['theme']");

String theme =
        expression.getValue(context, String.class);
~~~

The result is **dark**. The #settings variable holds the Map, and the string theme is the key used for lookup.

## Reading Variables with lookupVariable(...)

The **lookupVariable(String name)** API of EvaluationContext allows the application to read a variable's value from Java rather than from an expression:

~~~java
context.setVariable("requestId", "REQ-1024");

Object requestId =
        context.lookupVariable("requestId");
~~~

The name passed to lookupVariable does not have the # symbol. This is a Java-side variable read operation; it differs from writing **#requestId** inside a SpEL string.

For example, the application can retrieve a variable from the context for logging or passing into another processing step. If the variable has not been declared or has a null value, the lookup result can be null. When you need to distinguish between those two cases, manage the variable declaration state explicitly in application code instead of relying on a null return value to infer it.

## Null Variables and Undeclared Variables

A variable can be declared with a null value:

~~~java
context.setVariable("middleName", null);

Expression expression =
        parser.parseExpression("#middleName == null");

Boolean isMissing =
        expression.getValue(context, Boolean.class);
~~~

The expression checks whether the variable has a null value. However, when a variable is not declared, referencing it also fails to supply a value to the expression and can lead to an evaluation error depending on the usage context.

If a variable is an optional input, clearly decide how to represent the missing state: set the variable to null, provide a default value, or only build the expression after validating the data. You should not let a missing variable turn into an obscure error in the middle of a business flow.

You can use the null-safe operator when accessing a property on a variable that may be null:

~~~java
context.setVariable("customer", null);

Expression expression =
        parser.parseExpression("#customer?.email");

String email =
        expression.getValue(context, String.class);
~~~

When customer is null, the null-safe access returns null instead of attempting to read email on a nonexistent object. The null-safe syntax must be supported by the Spring version in use.

## Variables and Special Variables #root, #this

**#root** and **#this** are special variables managed by SpEL:

- **#root** references the initial root object of the evaluation.
- **#this** references the current target object at the evaluation position; it can change during selection or projection.
- **#myVariable** references a variable provided by the application in EvaluationContext.

Example in selection:

~~~java
Expression expression = parser.parseExpression(
        "#products.?[#this.price >= #root.minimumPrice]");
~~~

Here, #this is the current Product being evaluated, while #root is the initial object containing the collection and the price threshold. If the application has a **#minimumPrice** variable, the expression can also use that variable instead of the root object's property.

Do not confuse application-defined business variables with these two special variables. Using clear names like #minimumPrice, #currentUser, or #featureEnabled makes expressions easier to understand.

## Passing Variables into Each Evaluation

You can set the root object when creating StandardEvaluationContext and put variables into the same context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(product);

context.setVariable("minimumPrice", new BigDecimal("50.00"));

Expression expression =
        parser.parseExpression("price >= #minimumPrice");

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

You can also pass the root object at the time getValue is called:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumPrice", new BigDecimal("50.00"));

Boolean result =
        expression.getValue(context, product, Boolean.class);
~~~

The second approach fits when the same context holding variables or configuration is reused across multiple different root objects. If the context holds request-specific data, manage its lifecycle so values from a previous request are not mistakenly reused.

## Variables in Spring Integrations

SpEL is used across many Spring integration points, but the available variables depend on each integration. Not every variable name automatically exists in every EvaluationContext.

For example, in Spring Cache, expressions can access method parameters by names such as **#isbn**, **#p0**, or **#a0** depending on configuration and parameter name discovery capability. In other expressions, the framework may provide a root object and variables according to its own context.

Example:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(String isbn) {
    // Load book
}
~~~

Here, #isbn references the method parameter in the evaluation context prepared by Spring Cache. The application does not need to call setVariable itself inside this method.

When writing SpEL for annotations, refer to the list of variables provided by that specific integration. Do not assume a Spring Cache variable is also present in @Value or in a manually created EvaluationContext.

## Registering Functions and Their Relationship with Variables

StandardEvaluationContext also supports registering functions so expressions can invoke them using the **#functionName(...)** syntax. A function is registered under a name in the context and referenced in the expression with the # symbol, similar to a variable.

General example:

~~~java
Method normalizeMethod =
        TextFunctions.class.getDeclaredMethod(
                "normalize", String.class);

context.registerFunction("normalize", normalizeMethod);

Expression expression =
        parser.parseExpression("#normalize('  Spring  ')");

String normalized =
        expression.getValue(context, String.class);
~~~

A function needs to be a method compatible with SpEL's registration mechanism, usually a static method. This differs from a variable holding a String or an object: a variable provides a value, whereas a function provides callable behavior. Only register functions that the expression genuinely needs and that have a clear contract.

## EvaluationContext Lifecycle and Sharing

EvaluationContext can hold variables, a root object, and access configurations. Therefore, you need to clearly determine whether a context is created once for reuse or created separately for each evaluation.

If an application updates variables per request while sharing a single mutable StandardEvaluationContext across multiple threads, request data can overwrite one another. An expression could read a variable just modified by another request, leading to unstable results.

Safer ways to organize this:

- Create a dedicated context per request or evaluation when variables hold per-request data.
- Only share a context whose configuration is stable and whose variables are not modified while multiple threads are using it.
- Pass per-evaluation data in the root object or a new context.
- Avoid keeping sensitive objects or short-lived objects in a long-lived shared context.

A parsed Expression can be reused, while EvaluationContext and variable values should match each evaluation. Do not confuse reusing an Expression with every context being safe to share concurrently.

## Controlling Data Put into Variables

A variable can hold any object the application puts into the context. If an expression comes from an untrusted source, providing an object with many methods or references to services can significantly expand what the expression can do.

If only reading data is needed, put small DTOs with the required properties into the context. Avoid providing repositories, services, connections, or objects capable of manipulating resources. Choose a context with a restricted access surface and only enable method invocation when there is a specific requirement.

Variables do not create a security boundary on their own. The actual capabilities of an expression depend on the root object, property accessors, method resolvers, type locator, bean resolver, and capabilities provided by EvaluationContext.

## Handling Errors When Reading Variables

Errors can occur when an expression references an unprovided variable, accesses a nonexistent property on an object stored in a variable, or calls a method not supported by the context.

Parse errors and evaluation errors should be separated:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#customer.email");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    String email =
            expression.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate expression with current variables", ex);
}
~~~

ParseException indicates the SpEL string is syntactically invalid. EvaluationException indicates the expression cannot be evaluated with the current variables, root object, or context. When logging, record the expression identifier and relevant variable names, avoiding logging full values if variables contain personal data or secrets.

## When Should Variables Be Used?

Variables are suitable when:

- Values change per request or evaluation.
- The expression needs data that does not belong to the root object.
- You want to reuse the same Expression with different parameters.
- You need to pass a collection, Map, or small object into an expression.
- You want to separate configuration and parameters from a fixed SpEL string.

If data already belongs to a clear business object, accessing properties of the root object may be more natural. If logic requires many operations or multiple business steps, move the processing to Java rather than putting too many variables into a long expression.

## Conclusion

Variables in SpEL are declared on EvaluationContext, typically with **setVariable(name, value)**, and read in expressions using the **#name** syntax. Variables can hold simple values, collections, or objects; expressions can use them in arithmetic, comparisons, property access, and collection operations.

Distinguish variables from #root properties, the special variable #this, and bean references. Manage the EvaluationContext lifecycle carefully when variables hold per-request data, do not share mutable contexts across threads if variables can change, and expose only the data necessary for the expression. This keeps expressions flexible while maintaining clear data sources and evaluation behavior.
