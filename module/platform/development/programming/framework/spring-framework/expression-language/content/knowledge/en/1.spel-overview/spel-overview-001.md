# What Is Spring Expression Language (SpEL) and What Problem Does It Solve

Spring Expression Language (SpEL) is an expression language provided by Spring for reading, computing, and manipulating application data at runtime. An expression can retrieve a property from an object, invoke a method, compare values, perform calculations, access elements in a collection, or combine multiple conditions to return a result.

SpEL helps Spring and applications describe concise rules right where configuration or behavior declarations need them. Instead of writing extra Java snippets just to retrieve a value or check a simple condition, we can declare an expression and let Spring evaluate it against actual data.

## The Problem SpEL Solves

In a Spring application, many decisions depend on object state or configuration at runtime:

- A configuration value needs to be computed from another property, a system property, or a bean.
- A behavior should execute only when an object satisfies a specific condition.
- A cache key needs to be derived from a method parameter.
- A rule needs to read nested data inside an object or collection.
- An annotation needs to reference a parameter, return value, or information of the current object.

If everything were handled in Java, each place might need additional getters, conditional statements, calculations, or data-wiring code. For short and declarative rules, that approach makes configuration longer and obscures the intent of the configuration.

SpEL provides a unified representation for those expressions. Spring can evaluate an expression when creating a bean or at the corresponding integration point; an application can also explicitly parse and evaluate expressions using the API.

## How Does SpEL Work?

You can picture using SpEL through three components:

1. **Expression parser** takes an expression string and parses its syntax. The commonly used API is **SpelExpressionParser**.
2. **Expression** is the parsed representation. We can retrieve its value, retrieve its value as a desired type, or assign a value if the expression allows it.
3. **Evaluation context** provides the environment for evaluating the expression: the root object, variables, functions, property access mechanisms, bean resolution, and permitted capabilities.

The root object is called the **root object**. If an expression says **status == 'PAID'**, SpEL looks for the **status** property on the root object or in the provided context. Variables are referenced with the **#** symbol, for example **#customerId**. In some integrations, Spring prepares an appropriate root object and variables for that context automatically.

A standalone usage flow typically consists of: creating a parser, parsing the expression, creating an evaluation context with the data to evaluate, and retrieving the result. You can parse an expression once and reuse the Expression object across multiple evaluations.

## Standalone Usage Example

Suppose an application has an order with a status and a total amount. We want to check whether the order is eligible to move to the shipping step.

~~~java
public class Order {
    private final String status;
    private final BigDecimal total;

    public Order(String status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

SpEL can be used to express the condition:

~~~java
Order order = new Order("PAID", new BigDecimal("120.00"));

ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext(order);

Expression expression =
        parser.parseExpression("status == 'PAID' and total > 0");

Boolean canShip = expression.getValue(context, Boolean.class);
~~~

Here, **order** is the root object. The expression reads two properties, compares the status and total amount, and then returns a Boolean result. Java still creates the object and decides how to handle the result; SpEL handles expressing and evaluating the condition.

This example also shows that SpEL does not automatically know about application data. For an expression to access a property or variable, the application must provide an appropriate object or context.

## SpEL When Integrated with Spring

SpEL's strength is that it is used directly across many Spring mechanisms. In Spring annotations or configuration, expressions are commonly placed inside **#{...}**.

For example, retrieving a system property to assign to a bean:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

The example above instructs Spring to evaluate the expression and inject the result into the field. SpEL can also reference properties of another bean, perform calculations, or select values conditionally.

Another example comes from Spring Cache:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(String isbn) {
    // Load book
}
~~~

**#isbn** references the method parameter. Spring uses that value as the cache key. As a result, the key generation rule is declared directly on the annotation without writing a separate key-generator class for simple cases.

Spring Security also uses SpEL in authorization expressions such as **@PreAuthorize**. This is an example of how modules across the Spring ecosystem share a common expression language to describe conditions in each module's own context.

Note: the **#{...}** syntax is how expressions are embedded in Spring integration points. When calling the parser API directly, we normally pass the inner expression, such as **status == 'PAID'**, without wrapping it in **#{...}**.

## Main Capabilities

At a high level, SpEL supports the following groups of operations:

- **Data access:** reading properties, invoking methods, navigating nested properties, and accessing elements of an array, list, or map.
- **Computation and comparison:** arithmetic, comparison, and logical operators, type checking, regular expressions, and ternary conditions.
- **Context references:** using the root object, variables such as **#name**, or bean references such as **@someBean** when permitted by the evaluation context.
- **Working with collections:** filtering elements with selection, transforming elements with projection, and accessing elements by index.
- **Interacting with types:** in an appropriate context, referencing Java types, constructing objects, or invoking functions exposed to the expression.

For example, **items.?[active]** selects elements whose **active** property is true; **items.![name]** creates a new collection containing the **name** value of each element. These are useful operations when describing filtering or data extraction without writing loops in configuration.

Not every evaluation context allows all of the capabilities above. Actual capabilities depend on the context type, property accessors, method resolvers, bean resolvers, and components registered by the application.

## Distinguishing SpEL from Property Placeholders

In Spring configuration, two common syntaxes serve different purposes:

- **Property placeholder** **${app.page-size:20}** retrieves a configuration value from a property source, optionally using a default value if the property is not declared.
- **SpEL** **#{...}** evaluates an expression. The expression can read data, perform calculations, or combine multiple values.

For example:

~~~java
@Value("${app.page-size:20}")
private int pageSize;

@Value("#{T(java.lang.Math).max(10, 2 * 8)}")
private int calculatedLimit;
~~~

The first field receives the configuration value **app.page-size**, defaulting to **20**. The second field receives the result of the SpEL expression. Property placeholders are suited for bringing configuration values into an application; SpEL is suited when calculations or logic need to be expressed over those values.

## When Should You Use SpEL?

SpEL is suitable when an expression is short, declarative, and located at a clear integration point, such as:

- Computing a configuration value from existing values.
- Declaring a condition or key in an annotation supported by Spring.
- Accessing a property or parameter in a context provided by the framework.
- Filtering or extracting data from a collection in a simple expression.
- Allowing a small rule to be configured without creating an extra Java class just to perform a calculation or comparison.

You should move logic to Java when a rule has multiple branches, multiple processing steps, needs to call multiple services, requires complex error handling, or needs to be tested and reused as an explicit part of business logic. A long expression can be harder to read, harder to debug, and hide dependencies more than a clearly named Java method.

SpEL is an expression language; it does not replace all of Java and does not automatically turn an application into a business rules engine. It works best at the points the framework was designed to accept expressions.

## Evaluation Context and Safety

The evaluation context determines what an expression is allowed to see and do. **StandardEvaluationContext** provides broad capabilities, including property access, method invocation, and other extension mechanisms. That is convenient for expressions controlled by developers, but it also means expressions can have significant access to the application.

You should not take arbitrary expressions from users and evaluate them with a broadly privileged context. If you need to evaluate externally provided expressions, restrict the root object, variables, and exposed properties; register only the accessors or resolvers that are necessary. You can consider **SimpleEvaluationContext** for data binding scenarios that need a restricted subset of capabilities. This context does not provide all capabilities of **StandardEvaluationContext**, such as type references, constructors, and bean references; method access is also restricted according to configuration.

For repeatedly used expressions, you should parse once in advance and reuse the **Expression** rather than creating a parser and re-parsing the string on every call. The context and root object still need to match each evaluation. This reduces repeated parsing work and clarifies the boundary between the expression and input data.

## Conclusion

SpEL is the expression language layer that helps Spring connect declarative configuration with actual application data and state. It addresses the need to read properties, compute values, and describe conditions at integration points such as **@Value**, Spring Cache, and Spring Security. Used within the right scope, SpEL makes configuration concise and flexible; when logic becomes complex or untrusted input must be evaluated, processing should be moved to Java or the evaluation context must be strictly restricted.
