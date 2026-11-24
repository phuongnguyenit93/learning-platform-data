# Expressions, EvaluationContext, and Evaluation Results in Spring Expression Language

Spring Expression Language (SpEL) allows writing an expression as a string and evaluating that expression against application data. To understand how SpEL works, it is necessary to look clearly at the relationship between three components:

1. **Expression:** describes the calculation or condition to be performed.
2. **EvaluationContext:** provides the data and rules for SpEL to understand names, properties, methods, and operations in the expression.
3. **Evaluation Result:** the value obtained after the expression is executed in a specific context.

These three components connect in a flow: parse the expression string into an Expression object, pass that object into a context for evaluation, and receive the result.

## 1. Overall Execution Flow

An application typically uses SpEL in the following steps:

~~~text
Expression string
      |
      v
ExpressionParser.parseExpression(...)
      |
      v
Expression object
      |
      | getValue(EvaluationContext, ...)
      v
EvaluationContext provides data and access mechanisms
      |
      v
SpEL evaluates the expression
      |
      v
Result: Boolean, Number, String, object, collection, null, ...
~~~

For example, the string:

~~~spel
total >= #minimum && status == 'PAID'
~~~

describes the condition: the total amount of the current object must reach the minimum threshold and the order status must be PAID.

The expression string itself does not know which object total belongs to, what value #minimum has, or how status is read. Those details are supplied at evaluation time through EvaluationContext.

### Parsing and Evaluation Are Two Different Points in Time

- **Parsing:** ExpressionParser reads the string, checks syntax, and creates an Expression object representing the expression structure. This step does not yet need to compute a result for a specific order.
- **Evaluation:** the application calls getValue(...). SpEL uses the parsed expression together with the provided context to access data, execute operations, and return a value.

Therefore, an expression can be parsed once and evaluated many times with different objects or contexts.

## 2. What Does an Expression Describe?

Expression is the parsed representation of a SpEL expression. An application creates it through ExpressionParser, typically SpelExpressionParser.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");
~~~

Here:

- parser is responsible for parsing syntax.
- parseExpression(...) takes a SpEL string and returns an Expression.
- expression holds the structure to be evaluated later.

An expression can contain many kinds of elements:

| Element | Example | Meaning |
|---|---|---|
| Property | total, customer.name | Reads data from the target object |
| Variable | #minimum | Reads a value registered in the context |
| Literal | 100, 'PAID', true | A value written directly in the expression |
| Operator | +, >, && | Computes or combines conditions |
| Method call | name.toUpperCase() | Invokes a method if permitted by the context |
| Type access | T(java.time.LocalDate) | References a Java type according to context capabilities |

An Expression does not self-contain all the data needed to run. For instance, total is looked up on the root object in the context; whereas #minimum is looked up in the context's variable set.

## 3. EvaluationContext Provides the Execution Environment

EvaluationContext defines the environment in which an expression is evaluated. It helps SpEL answer questions such as:

- Which object is the root object?
- Which variables have been declared and what are their values?
- How can properties be read or methods invoked?
- How can data types be converted?
- Can Java types, constructors, or beans be referenced?

### 3.1. Root Object

The root object is the default object on which property names without a variable prefix are looked up.

For example:

~~~spel
total >= 500000
~~~

If the root object is an Order, SpEL looks for the total property on that object. In Java, reading a property is typically performed through the corresponding getter, for example getTotal().

You can set the root object when creating the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

Or pass the root object directly to an overload of getValue(...):

~~~java
Boolean result =
    expression.getValue(context, order, Boolean.class);
~~~

Inside an expression, #root references the current root object. For example, #root.total explicitly states that total is read from the root object.

### 3.2. Variables in the Context

Variable names in SpEL have the # prefix. The application registers a variable on EvaluationContext and then references that variable in the expression.

~~~java
context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

The expression can use the newly registered variable:

~~~spel
total >= #minimum
~~~

If the expression references #minimum but the context does not have a corresponding variable, evaluation may fail. Therefore, the expression and the context must agree on variable names.

### 3.3. #root and #this

These two special variables help identify the object the expression is working on:

- #root always references the root object of the evaluation.
- #this references the object that is currently the evaluation target. In expressions operating on collections such as selection or projection, #this can change for each element.

For example, when filtering orders in a collection:

~~~spel
orders.?[total >= #minimum]
~~~

The condition inside ?[...] is evaluated in turn on each element of orders. Within the scope of that condition, total and #this.total both refer to the property of the element currently being examined. #root still refers to the initial root object.

### 3.4. Other Components of EvaluationContext

Besides the root object and variables, the context can also configure the following mechanisms:

| Mechanism | Role |
|---|---|
| PropertyAccessor | Defines how properties are read or written |
| MethodResolver | Defines how methods to invoke are located |
| ConstructorResolver | Defines how constructors are located |
| TypeLocator | Locates Java types referenced in the expression |
| TypeConverter | Converts values between compatible types |
| BeanResolver | Resolves bean references, such as the @myBean syntax when configured |
| OperatorOverloader | Customizes how certain operators are handled |

StandardEvaluationContext provides a full-featured and deeply configurable SpEL environment. SimpleEvaluationContext provides a more restricted environment, suitable for data binding scenarios where allowed features need to be controlled. Choosing the context type determines which capabilities an expression can use.

## 4. Evaluation Result

The result is the value that Expression returns after being evaluated in a context. The result type depends on the expression and actual data, and can be:

- A Boolean logical value.
- An integer, floating-point number, or another numeric type.
- A String.
- A Java object.
- A collection or array.
- null, if the expression is valid and the computed value is null.

For example:

~~~spel
total >= #minimum
~~~

returns true or false if the necessary values can be read and compared.

Meanwhile:

~~~spel
customer.name
~~~

can return a String, depending on the actual object and property.

The result is not fixed merely at parse time. The same Expression can return different results when evaluated with different root objects or variables.

### Retrieving Untyped and Typed Results

If getValue(...) is called without specifying a desired type, the method returns Object:

~~~java
Object value = expression.getValue(context);
~~~

If the application knows the expected result type, it can request that type:

~~~java
Boolean value =
    expression.getValue(context, Boolean.class);
~~~

SpEL uses the context's type conversion mechanism when needed and when possible. If the result cannot be converted to the requested type, evaluation may raise an error. Thus, the target type in getValue(...) both makes Java code clearer and expresses the type contract expected by the application.

## 5. Complete Example: Combining Expression, EvaluationContext, and Result

Suppose the application has an Order class:

~~~java
public class Order {
    private final BigDecimal total;
    private final String status;

    public Order(BigDecimal total, String status) {
        this.total = total;
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }
}
~~~

The application wants to check whether an order is considered eligible for processing. The condition is that the total amount reaches the minimum threshold and the status is PAID.

~~~java
Order order = new Order(
    new BigDecimal("750000"),
    "PAID"
);

// 1. Parse the string into an Expression.
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "total >= #minimum && status == 'PAID'"
);

// 2. Create a context with Order as the root object.
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

// 3. Provide the variable the expression needs to use.
context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

// 4. Evaluate and retrieve the Boolean result.
Boolean eligible =
    expression.getValue(context, Boolean.class);
~~~

You can read the example following the exact relationship among the three components:

1. **Expression:** the expression requires reading total, comparing with #minimum, and then checking status.
2. **EvaluationContext:** provides order as the root object and registers the variable minimum with the value 500000. The context also provides the mechanisms for SpEL to access properties and perform comparisons.
3. **Evaluation Result:** because total is 750000 and status is PAID, the eligible result is true.

If minimum is changed to 900000, there is no need to re-parse the expression. Simply evaluating with the new variable value will yield false. Similarly, the same Expression can be used with a different Order by creating a new context for that order.

## 6. Relationship Among the Three Components When Data Changes

You can visualize each component's role by keeping two components constant and changing the remaining one:

| Change | What Happens? |
|---|---|
| Change the expression string | The parser creates a different Expression describing different logic |
| Keep the Expression, change the root object | Properties are read from the new object; the result may change |
| Keep the Expression, change variables in the context | Parts referencing variables receive new values; the result may change |
| Keep the Expression and context, re-evaluate | SpEL recalculates using the data the context provides at evaluation time |
| Request a different result type | SpEL attempts to return or convert the result to the target type if compatible |

The key point is that Expression describes the logic, while EvaluationContext provides the environment and data to run that logic. The result is the output of combining both components at a specific evaluation.

## 7. Reusing Expression and Managing EvaluationContext

When an expression is used repeatedly, applications usually parse it once and reuse the Expression object. This avoids having to re-parse the same string on every execution.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");

// For each processing run, provide an appropriate context.
StandardEvaluationContext firstContext =
    new StandardEvaluationContext(firstOrder);
firstContext.setVariable("minimum", minimum);

Boolean firstResult =
    expression.getValue(firstContext, Boolean.class);

StandardEvaluationContext secondContext =
    new StandardEvaluationContext(secondOrder);
secondContext.setVariable("minimum", minimum);

Boolean secondResult =
    expression.getValue(secondContext, Boolean.class);
~~~

A context can hold a root object and mutable variables. Therefore, an application should manage the lifecycle of the context to match the data of each evaluation, avoiding accidentally reusing variables or the root object from one request for another request. Especially in web applications handling many concurrent requests, consider creating a separate context for each processing call or scope of work.

## 8. At Which Stage Can Errors Occur?

Separating parsing and evaluation makes it easier to identify the cause of an error:

- **Parsing errors:** the expression string has invalid syntax, such as missing parentheses or an invalid operator. The error occurs when calling parseExpression(...).
- **Evaluation errors:** the syntax is valid, but the data or environment does not satisfy the requirements, such as an unregistered variable, a nonexistent property, an unsuitable method call, or a failed type conversion. The error occurs when calling getValue(...).

Some useful questions when troubleshooting errors:

1. Was the expression string parsed successfully?
2. Is the root object of the right type and does it have the properties the expression needs?
3. Have all #... variables been registered with the exact names?
4. Does the EvaluationContext type in use allow the features requested by the expression?
5. Is the requested result type compatible with the actual value?

## 9. Common Misconceptions

**Misconception 1: Calling parseExpression(...) already runs the expression.**  
Parsing only builds the expression structure. Value computation happens when calling getValue(...).

**Misconception 2: Assuming variables in an expression automatically have values.**  
Names with the # prefix must be supplied in the context, except for special variables defined by SpEL.

**Misconception 3: Assuming every property name is a variable.**  
total is usually looked up on the root object or current object; #minimum is looked up as a variable in the context. The two forms have different meanings.

**Misconception 4: Assuming an Expression has only one fixed result.**  
The result is produced at evaluation time and depends on the root object, variables, and environment of that evaluation.

**Misconception 5: Assuming the result type is always determined solely from the expression string.**  
The expression structure can predict the value kind in many cases, but the actual value and type still depend on runtime data. The getValue(..., Class<T>) overload expresses the type the application expects to receive.

## 10. Takeaways

- ExpressionParser parses strings and creates Expression objects.
- Expression describes the logic to evaluate and does not supply application data on its own.
- EvaluationContext supplies the root object, variables, and rules for access, conversion, method invocation, or type resolution.
- getValue(...) combines Expression with a context (and optionally a root object or desired result type) to perform evaluation.
- Evaluation result is the value produced for that evaluation; the same expression can produce different results when the context or data changes.
- Distinguish parsing errors from evaluation errors to pinpoint the stage causing the issue.

When reading or writing SpEL code, follow three questions: **What does the expression ask for? What data and capabilities does the context provide? What value does this evaluation return?** Answering those three questions means grasping the core relationship among Expression, EvaluationContext, and Evaluation Result.
