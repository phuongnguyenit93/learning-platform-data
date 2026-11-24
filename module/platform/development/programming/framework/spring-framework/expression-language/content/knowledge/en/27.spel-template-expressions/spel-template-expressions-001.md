# Distinguishing Plain Expressions from Template Expressions

Spring Expression Language (SpEL) supports two common ways of parsing strings: **plain expressions** and **template expressions**. A plain expression treats the entire input string as SpEL syntax. A template expression allows mixing ordinary text with one or more SpEL segments enclosed between a pair of delimiters.

This distinction matters when an application needs to compute a logical value or when it wants to generate display content containing both static text and dynamic data. The same string can be parsed differently depending on the **ParserContext** passed to the parser.

## What Is a Plain Expression?

A plain expression is a string whose entire content is interpreted according to SpEL syntax. When using the **parseExpression(String)** overload, the parser does not by default treat text segments outside a delimiter pair as static template content.

For example, an arithmetic expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 * (5 + 2)");

Integer result =
        expression.getValue(Integer.class);
~~~

The entire string **10 * (5 + 2)** is the expression. SpEL parses the syntax, evaluates the operation, and returns the result 70.

A plain expression can also read a property or a variable:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

Expression expression =
        parser.parseExpression("#name.toUpperCase()");

String result =
        expression.getValue(context, String.class);
~~~

Here, the entire string **#name.toUpperCase()** is SpEL syntax. There is no static text portion that needs to be preserved and concatenated with the result.

## What Is a Template Expression?

A template expression allows combining ordinary text with SpEL expression segments. The parser recognizes the segments to evaluate via an opening and closing delimiter pair specified by **ParserContext**.

With Spring's default template configuration, the delimiter pair is **#{** and **}**. The content between the two delimiters is parsed as a plain expression; the text outside is preserved as literal content.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

Expression template = parser.parseExpression(
        "Hello, #{#name}!",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

The result is **Hello, An!**. The parser keeps the text **Hello, ** and **!**, while evaluating the **#name** segment and inserting the result into the right position.

If the string **Hello, #{#name}!** is passed to the parseExpression(String) overload without a template context, the entire string will be treated as plain expression syntax. The ordinary text is not valid SpEL syntax in that position, so the parser may throw a ParseException.

## Comparing the Two Parsing Modes

| Characteristic | Plain expression | Template expression |
|---|---|---|
| Common invocation | **parseExpression(String)** | **parseExpression(String, ParserContext)** |
| How the string is interpreted | The entire string is SpEL | Mixes literal text with SpEL segments |
| Delimiters | No template delimiters needed | Uses prefix/suffix from ParserContext |
| Typical result | Value of the expression | String constructed from text and embedded segment results |
| Use case | Calculations, conditions, data access | Messages, labels, configuration content with dynamic data |

Both approaches use the same SpEL language inside expression segments. The difference lies in how the parser splits the input string into literal parts and parts to evaluate.

## ParserContext and TemplateParserContext

The second overload of the parser has the form:

~~~java
Expression parseExpression(
        String expressionString,
        ParserContext context);
~~~

**ParserContext** provides information so the parser knows whether the input string is a template and, if it is a template, which delimiters to use.

This interface has the main methods:

- **isTemplate()**: indicates whether the string should be parsed in template mode or plain expression mode.
- **getExpressionPrefix()**: returns the opening delimiter of an expression segment.
- **getExpressionSuffix()**: returns the closing delimiter of an expression segment.

Spring provides **TemplateParserContext** to use templates conveniently:

~~~java
ParserContext parserContext =
        new TemplateParserContext();

Expression template = parser.parseExpression(
        "Order total: #{#total}",
        parserContext);
~~~

The default constructor of TemplateParserContext uses prefix **#{** and suffix **}**. Different delimiters can be passed when an application wants a custom template syntax:

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
        "Order total: [[#total]]",
        parserContext);
~~~

In the example, **[[** opens the SpEL segment and **]]** closes it. The remaining text stays literal text.

Custom delimiters only take effect when the parser is passed the corresponding ParserContext. If the default parser is used without passing a context, the parser does not automatically infer that **[[...]]** is a template segment.

## Templates Can Contain Multiple Expression Segments

A template can contain multiple SpEL segments interspersed with static text:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customer", "An");
context.setVariable("orderId", "ORD-1024");
context.setVariable("total", new BigDecimal("250.00"));

Expression template = parser.parseExpression(
        "Customer #{#customer}, order #{#orderId}, "
        + "total amount #{#total}",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

The result looks like:

~~~text
Customer An, order ORD-1024, total amount 250.00
~~~

Each segment between delimiters is evaluated in the same EvaluationContext. Variables can be reused across multiple segments. If a variable does not exist or a property cannot be accessed, template evaluation may fail at the corresponding expression segment.

Multiple embedded segments help build flexible messages without concatenating strings in Java. However, if a template has too many branches or complex business logic, it is better to compute values in Java first and pass simple results into the context.

## Literal Text Is Preserved, Expressions Are Evaluated

You can picture the parser processing a template in two parts:

1. Text outside the delimiters is preserved as-is.
2. Content inside each pair of delimiters is parsed and evaluated as a SpEL expression.

Example:

~~~text
Status: #{#status}, quantity: #{#quantity}
~~~

If **#status** is **PAID** and **#quantity** is 3, the result is:

~~~text
Status: PAID, quantity: 3
~~~

The characters **Status: **, **, quantity: **, and punctuation are static text. The two variables are dynamic content.

Templates are useful when building display strings, without changing the rules of the embedded expressions. Inside the delimiters, you can still use property access, operators, method calls, or other SpEL features allowed by EvaluationContext.

## Template Expressions in Spring Configuration

In many Spring integration points, expressions are written between **#{...}**. For example with @Value:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

Spring processes the content inside **#{...}** as a SpEL expression and injects the result into the field. This is how expressions are embedded in Spring's configuration mechanism; the application does not need to create a parser itself when the annotation is already handled by Spring.

A template with static text mixed with expressions can also be used in integration points that support template parsing:

~~~java
@Value("Running on system #{systemProperties['os.name']}")
private String environmentLabel;
~~~

Exact capabilities depend on the integration point and how it configures the expression resolver. When using the parser API directly, pass ParserContext explicitly if the string has literal text outside the expression segments.

## Distinguishing Template Delimiter #{...} from Property Placeholder ${...}

In Spring configuration, two notations that are easily confused are **#{...}** and **${...}**:

- **#{...}** is used to embed a SpEL expression at an integration point that supports SpEL.
- **${...}** is a property placeholder, used to retrieve values from configuration sources such as properties or environment.

Example:

~~~java
@Value("${app.name:Demo}")
private String applicationName;

@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

The first field retrieves the **app.name** property and uses **Demo** as the default value if the property has not been declared. The second field evaluates a SpEL expression to read the user.timezone system property.

The two mechanisms can be combined in certain Spring configurations, but they solve two different tasks. Property placeholders substitute configuration values; SpEL evaluates expressions against data and context.

If you need to perform calculations on an injected property, you can use a placeholder as input to an expression at an integration point that supports both mechanisms. Rely on the processing order of the specific integration, and do not assume every parser API automatically understands both delimiter types.

## Plain Expressions Can Contain String Literals

A plain expression can still return a string. That does not turn it into a template expression:

~~~java
Expression expression =
        parser.parseExpression("'Hello, Spring!'");

String result =
        expression.getValue(String.class);
~~~

The entire string enclosed in single quotes is a SpEL string literal. The result is **Hello, Spring!**.

The difference is that a template preserves text outside the delimiters without requiring it to be written as a string literal in SpEL syntax. When writing free-form text mixed with multiple expressions, templates are usually easier to read than concatenating string literals with the **+** operator.

Example of a plain expression concatenating strings:

~~~java
Expression expression =
        parser.parseExpression(
                "'Hello, ' + #name + '!'");
~~~

The same display goal can be written as a template:

~~~java
Expression template = parser.parseExpression(
        "Hello, #{#name}!",
        new TemplateParserContext());
~~~

The template approach directly shows the static text and dynamic data positions. The plain expression approach expresses the entire string concatenation operation using SpEL syntax.

## When a Template Contains Only One Expression Segment

If the goal is only to evaluate an expression, with no interspersed static text, using **parseExpression(String)** is usually simpler:

~~~java
Expression expression =
        parser.parseExpression("#total * 1.08");

BigDecimal result =
        expression.getValue(context, BigDecimal.class);
~~~

There is no need to add template delimiters when the entire string is already SpEL syntax.

TemplateParserContext is used when the string needs both ordinary text and evaluated expression parts. Choosing the right parsing mode helps avoid syntax errors and clarifies the intent of the input string.

## Parse Errors and Evaluation Errors

Both plain expressions and template expressions can fail at two stages:

- **ParseException:** the string has invalid syntax. For templates, errors can result from mismatched delimiters, invalid syntax in an inner expression segment, or an unsuitable ParserContext.
- **EvaluationException:** the expression parsed successfully but cannot be evaluated with the current data or EvaluationContext, for example an unprovided variable, a nonexistent property, or a method not permitted to be called.

Example:

~~~java
Expression template;

try {
    template = parser.parseExpression(
            "Hello, #{#customer.name}!",
            new TemplateParserContext());
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid template syntax", ex);
}

try {
    String message =
            template.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate template", ex);
}
~~~

Separating the two error types helps determine whether the issue lies in string structure or runtime data. If templates are stored in configuration, they can be parsed when loading configuration to detect syntax errors early; evaluation still requires a suitable context and data at runtime.

## Considerations When Designing Delimiters

The default delimiters **#{** and **}** are common in Spring. When using templates in a system with multiple template languages or other configurations, care is needed to avoid conflicts with syntax from other systems.

Some principles:

- Choose clear and consistent delimiters if custom delimiters are needed.
- Pass the same ParserContext when parsing every template that uses those delimiters.
- Ensure every expression segment has matching opening/closing delimiters.
- Avoid letting untrusted user text be misinterpreted as executable SpEL segments.
- Restrict what EvaluationContext allows embedded expressions to access.

Changing delimiters only changes how the parser identifies expression regions. It does not restrict the privileges of the expressions inside. If a template contains expressions from external sources, you must still control the context, root object, variables, accessors, and method resolvers.

## When to Use Plain Expressions vs. Templates?

Use **plain expressions** when:

- The entire input string is SpEL syntax.
- You need to compute a value, return a Boolean, or read a property.
- The expression is used as a key, condition, or configuration value.
- There is no static text portion that needs to be preserved.

Use **template expressions** when:

- You need to mix ordinary text with dynamic data.
- You want to generate messages, labels, or configuration strings containing SpEL segments.
- There are multiple expression regions embedded in the same string.
- You want literal text to remain readable without writing many concatenation operators.

If the string only needs to substitute a few simple placeholders from configuration, property placeholders or a dedicated template engine may be more suitable. If content generation logic has many branches, complex formatting, or requires localization, consider building the content in Java or using a specialized templating library.

## Conclusion

**Plain expressions** treat the entire string as SpEL syntax and are usually parsed with **parseExpression(String)**. **Template expressions** combine static text with SpEL segments and are parsed with **parseExpression(String, ParserContext)**. **TemplateParserContext** defaults to delimiters **#{** and **}**, while allowing other delimiter pairs to be configured.

Use plain expressions for calculations, conditions, and data access. Use templates when you need to place expression results inside ordinary text. Distinguish SpEL's **#{...}** from property placeholder's **${...}**, pass a ParserContext matching the delimiters, and restrict EvaluationContext when templates contain expressions from external sources.
