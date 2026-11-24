# Reading an Expression from a String with a Parser

In SpEL, **ExpressionParser** is the entry point for turning a character string into an expression object that can be evaluated. The application feeds SpEL syntax into the parser via the **parseExpression(...)** method. The returned result is an **Expression**, representing the parsed expression.

This process has two stages to distinguish:

1. **Parse:** the parser reads the string, checks the syntax, and builds an expression representation.
2. **Evaluate:** the application asks the Expression object to compute a value within an evaluation context and/or against a specific root object.

The parser does not execute the expression immediately upon receiving the string. Parsing produces an Expression; the result is only computed when the application calls a method such as **getValue(...)** or **setValue(...)**.

## Creating an ExpressionParser

Spring's common parser API is **SpelExpressionParser**, in the **org.springframework.expression.spel.standard** package. The **ExpressionParser** interface is in the **org.springframework.expression** package.

Minimal example:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("'Hello ' + 'Spring SpEL'");

String result = expression.getValue(String.class);
~~~

The string passed into **parseExpression(...)** is a SpEL expression. In the example, two string literals are concatenated together. The parser returns an Expression; the **getValue(String.class)** call is what requests evaluation of the expression and retrieves the result as a String.

The result is **Hello Spring SpEL**. This example does not need a root object or an evaluation context because the expression only contains literals and operations on literals.

## What does parseExpression take and return?

The basic method has the signature:

~~~java
Expression parseExpression(String expressionString);
~~~

The **expressionString** parameter is a string containing SpEL syntax. The result is an object implementing the **Expression** interface. This interface provides operations to read the value, read the value as a desired type, check writability, and update the value in cases where the expression permits it.

A few simple expression strings:

| String passed to the parser | Meaning |
|---|---|
| **'Spring'** | A string literal |
| **10 * 5** | Arithmetic multiplication |
| **name** | Reading the name property on the root object |
| **items[0]** | Accessing the first element of an appropriate collection or array |
| **status == 'ACTIVE'** | Comparing the status value with the string ACTIVE |
| **name.toUpperCase()** | Calling an instance method if the evaluation context allows it |

The strings in the first column are SpEL syntax passed as Java Strings. In Java code, you need to put quotes around the outer Java string and preserve the single quotes of the inner SpEL string literal when needed.

## Evaluating an expression without a root object

If an expression only contains literals, operators, or values that do not depend on external data, you can retrieve the result directly:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 * (5 + 2)");

Integer result = expression.getValue(Integer.class);
~~~

The parser creates an Expression from the string. When calling **getValue(Integer.class)**, SpEL computes the result and requests it to be returned as an Integer.

You can use **getValue()** to receive the result as an Object:

~~~java
Object result = expression.getValue();
~~~

The generic retrieval approach is useful when the result type is not known in advance, whereas in application code, specifying the desired type usually helps express the expression's contract clearly. Spring will use the evaluation context's type conversion mechanism when needed and when the conversion is supported.

## Evaluating an expression against a root object

Many expressions need to read data from an object. In that case, pass the root object to the value retrieval method:

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
        new Product("Keyboard", new BigDecimal("45.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String productName =
        expression.getValue(product, String.class);
~~~

Here, **product** is the root object. The **name** expression asks SpEL to read the corresponding property from the object. For a standard JavaBean, property reading can be performed through a getter.

If the expression needs to access multiple properties or perform a calculation, the syntax is parsed in the same way:

~~~java
Expression expression =
        parser.parseExpression("price > 0 and name != null");

Boolean valid =
        expression.getValue(product, Boolean.class);
~~~

The root object supplies the data that the expression references. If the expression mentions a nonexistent property or an operation incompatible with the actual data type, the error typically occurs during the evaluation stage, even though the string parsed successfully.

## Combining the parser with EvaluationContext

**EvaluationContext** provides the environment for evaluating expressions. The context can contain a root object, variables, property accessors, method resolvers, a type converter, and other components depending on the implementation.

For example, using **StandardEvaluationContext** to set a root object and a variable:

~~~java
Product product =
        new Product("Keyboard", new BigDecimal("45.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(product);

context.setVariable("minimumPrice", new BigDecimal("20.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("price >= #minimumPrice");

Boolean accepted =
        expression.getValue(context, Boolean.class);
~~~

In the expression, **#minimumPrice** references the variable added to the context. The root object is set when creating the context, so the expression can read the **price** property without passing the root object again.

Another approach is passing both the context and the root object at evaluation time:

~~~java
EvaluationContext context = new StandardEvaluationContext();
Boolean accepted =
        expression.getValue(context, product, Boolean.class);
~~~

Which approach you choose depends on whether the root object is fixed in the context or changes on each call. What matters is that the expression is evaluated in a context that has sufficient data and the access capabilities it requires.

## Parsing an expression and evaluating an expression are two different things

A string can be syntactically valid SpEL yet fail to evaluate successfully against a specific object.

For example, the parser can parse the string **unknownProperty > 10** because the expression structure is valid. When evaluated against a root object that has no **unknownProperty** property, SpEL may throw a property access error.

Therefore, you should distinguish two error categories:

- **Parse errors:** the string does not follow SpEL syntax, such as missing parentheses or invalid operators. The parser typically throws **ParseException**.
- **Evaluation errors:** the syntax parsed, but the operation cannot be performed in the current data or context, such as a nonexistent property, calling an unsupported method, or an incompatible operation. SpEL typically throws **EvaluationException** or a specific subclass.

Example of handling errors in both stages:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(expressionText);
} catch (ParseException ex) {
    // The expression string has invalid syntax
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Object value = expression.getValue(context, rootObject);
} catch (EvaluationException ex) {
    // The expression cannot be evaluated in this context/root object
    throw new IllegalStateException("Cannot evaluate SpEL", ex);
}
~~~

Separating the two stages helps determine whether the error lies in the expression string or in the data and execution environment.

## Reading the result as a desired type

The Expression interface has overloads of **getValue(...)** that allow specifying the result type:

~~~java
Expression expression =
        parser.parseExpression("price * 2");

BigDecimal doubledPrice =
        expression.getValue(context, product, BigDecimal.class);
~~~

By specifying the target type, the application clearly states the expected result. SpEL can use the context's type converter to convert the result if a suitable conversion exists. If the value cannot be computed or converted to the requested type, evaluation fails.

Do not treat the type parameter as a way to force any result into any type. The result type must be compatible with the expression value or have a supported conversion.

## Using the parser with template expressions

Normally, **parseExpression(String)** accepts a plain SpEL expression. If the string contains regular text interspersed with expression segments, pass an additional **ParserContext**.

Example using **TemplateParserContext**:

~~~java
import org.springframework.expression.common.TemplateParserContext;

Expression template = parser.parseExpression(
        "Hello, #{#name}!",
        new TemplateParserContext());

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("name", "An");

String message = template.getValue(context, String.class);
~~~

In this template, the outer text is preserved as-is; the segment inside **#{...}** is parsed and evaluated as SpEL. The result is **Hello, An!**.

Be sure to distinguish **#{...}** delimiters in templates from regular parser calls. If you pass **#{...}** into **parseExpression(String)** without providing a template parser context, the string is interpreted as plain expression syntax and may not parse as expected.

## Parse once, evaluate many times

If the same expression is used repeatedly, keep the Expression object after parsing instead of creating a parser and re-parsing the string on every call:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("price >= 100");

for (Product product : products) {
    Boolean expensive = expression.getValue(product, Boolean.class);
    // Process the result
}
~~~

Here, the string is parsed only once. On each iteration, the Expression is evaluated against a different root object. This organization separates the fixed syntax from data that varies per call and avoids repeated parsing work.

If the expression depends on variables or a context, make sure to supply an appropriate context on each evaluation. Avoid letting old variables or root objects accidentally affect a new request.

## Configuring the parser when controlling collection and null property access

In addition to the default constructor, **SpelExpressionParser** can accept a **SpelParserConfiguration**. This configuration controls certain behaviors during expression evaluation, such as auto-growing collections or auto-creating intermediate values when encountering null properties in supported cases.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

The two flags in the example demonstrate enabling auto-grow for null references and collections. This behavior can mutate objects or collections during evaluation, so enable it only when the application genuinely needs it. If the goal is simply reading an expression from a string and retrieving a result, the default parser is usually sufficient.

Parser configuration adjusts the parser's parsing/evaluation behavior; it does not replace EvaluationContext. The root object, variables, accessors, and exposed capabilities are still controlled at the context level.

## Notes when receiving expressions from external sources

The parser can receive strings from configuration, a database, or users. However, being able to parse a string does not mean that the expression is safe to evaluate in every context.

If an expression comes from an external source:

- Clearly define which data the expression is allowed to access.
- Use a small root object containing only the necessary data.
- Consider **SimpleEvaluationContext** if you only need data binding with a restricted feature set.
- Avoid exposing beans, services, or objects with privileges to perform sensitive operations.
- Limit the size and source of expressions, and handle both parse errors and evaluation errors.
- Enable extension capabilities only when the use case requires them and they are controlled.

**ExpressionParser** is responsible for converting a string into an Expression. EvaluationContext and the root object are what decide which data the expression can see and manipulate at runtime.

## Conclusion

To read a SpEL expression from a string, create an **ExpressionParser**, call **parseExpression(...)**, and obtain an **Expression**. Then call **getValue(...)** with the appropriate result type, root object, and evaluation context to evaluate the expression.

Separating parsing from evaluation enables reusing the Expression, categorizing errors clearly, and proactively controlling input data. For simple expressions, the default parser is sufficient; for data-dependent expressions, provide a root object or context. When strings come from external sources, restrict the operational surface using an appropriate context and accessors.
