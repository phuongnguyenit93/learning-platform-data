# Distinguishing plain expressions from template expressions

Spring Expression Language (SpEL) can parse a string in two modes: **plain expression** and **template expression**. With a plain expression, the entire string is interpreted as SpEL syntax. With a template expression, the string is split into static text and SpEL segments marked by delimiters; the parser preserves the static text and evaluates the embedded expression segments.

Choosing the right parsing mode avoids syntax errors and accurately expresses the string's purpose. Plain expressions are suitable when computing a value or checking a condition. Template expressions are suitable when building messages, labels, or content with fixed text mixed with dynamic data.

## Plain expressions

The **parseExpression(String)** overload treats the entire input parameter as a SpEL expression. The string must follow the language's syntax, even when the final result is a String.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 * (5 + 2)");

Integer result =
        expression.getValue(Integer.class);
~~~

The expression above performs a calculation and returns 70. The entire string **10 * (5 + 2)** is SpEL syntax; no text portion is preserved as template content.

A plain expression can also return a literal string:

~~~java
Expression expression =
        parser.parseExpression("'Hello, Spring!'");

String message =
        expression.getValue(String.class);
~~~

In this example, single quotes are SpEL's string literal syntax. The result is the string **Hello, Spring!**. The fact that the result has type String does not make the expression a template.

Another plain expression can read a variable and concatenate strings:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

Expression expression =
        parser.parseExpression("'Hello, ' + #name + '!'");

String message =
        expression.getValue(context, String.class);
~~~

The entire content is still parsed as a single expression. Text portions must be written as string literals and joined with the **+** operator.

## Template expressions

Template expressions allow mixing ordinary text with one or more SpEL segments. The parser identifies segments to evaluate using the delimiter pair provided via **ParserContext**.

Spring provides **TemplateParserContext** with default delimiters:

- Prefix: **#{**
- Suffix: **}**

The part between the prefix and suffix is parsed as a SpEL expression. Text outside the delimiters is preserved as literal text.

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

The result is **Hello, An!**. The parser preserves the text **Hello, ** and **!**, while evaluating **#name** and inserting the result into the corresponding position.

The important difference lies in the overload being called. A string containing free-form text mixed with **#{...}** delimiters must be parsed with a ParserContext in template mode. If **parseExpression(String)** is called, the entire string is treated as a plain expression and the text outside the delimiters can cause the parser to report a syntax error.

## Comparing the two modes

| Feature | Plain expression | Template expression |
|---|---|---|
| Common API | **parseExpression(String)** | **parseExpression(String, ParserContext)** |
| Input interpretation | The entire string is SpEL syntax | Static text mixed with SpEL segments |
| Delimiters | No template delimiters needed | Prefix/suffix provided by ParserContext |
| Writing text | Use string literals and concatenation operators | Write directly outside delimiters |
| Typical result | Value of the expression | String combining literal text and expression results |
| Suitable use cases | Calculations, conditions, data access | Messages, labels, and dynamic content |

Both modes use the same SpEL syntax inside the expression part. ParserContext only determines how the input string is split into parts to preserve verbatim and parts to parse/evaluate.

## What role does ParserContext play?

The overload with ParserContext has the form:

~~~java
Expression parseExpression(
        String expressionString,
        ParserContext context);
~~~

**ParserContext** describes how the parser processes the string. This interface provides three main pieces of information:

- **isTemplate()**: indicates whether the input is processed as a template.
- **getExpressionPrefix()**: returns the delimiter opening an expression segment.
- **getExpressionSuffix()**: returns the delimiter closing an expression segment.

**TemplateParserContext** is a built-in implementation so you do not have to write a custom ParserContext for common cases:

~~~java
ParserContext parserContext =
        new TemplateParserContext();

Expression template = parser.parseExpression(
        "Order: #{#orderId}",
        parserContext);
~~~

The default constructor uses **#{** and **}**. Other delimiters can be passed if the application's syntax needs to avoid conflicts with another template engine or configuration format.

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
        "Order: [[#orderId]]",
        parserContext);
~~~

In the example, **[[** opens the SpEL segment and **]]** closes it. The remaining text is preserved verbatim. Custom delimiters only take effect when the parser is passed the corresponding ParserContext; they do not automatically alter the default parser's syntax.

## Multiple expression segments in the same template

A template can contain multiple expression segments, each evaluated in the EvaluationContext passed when calling getValue:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customer", "An");
context.setVariable("orderId", "ORD-1024");
context.setVariable("total", new BigDecimal("250.00"));

Expression template = parser.parseExpression(
        "Customer #{#customer}, order #{#orderId}, "
        + "total #{#total}",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

The result has the form:

~~~text
Customer An, order ORD-1024, total 250.00
~~~

Embedded segments share the same EvaluationContext so they can read the same variables and root object. If one segment references an unprovided variable, reads a nonexistent property, or calls a method not permitted by the context, evaluation can fail.

Keep each expression segment short and focused on retrieving or computing a single value. If the template contains many business branches, compute the values in Java and place the simple results into the context.

## Concatenating plain expressions vs. template expressions

The same content can be written in either way.

Plain expression:

~~~java
Expression expression =
        parser.parseExpression(
                "'Customer ' + #customer + ', order ' + #orderId");

String message =
        expression.getValue(context, String.class);
~~~

Template expression:

~~~java
Expression template = parser.parseExpression(
        "Customer #{#customer}, order #{#orderId}",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

Both approaches can produce the same result. Plain expressions represent concatenation using SpEL syntax. Templates directly represent static text and dynamic data placeholders, which is usually more readable when text makes up most of the content.

If the string only contains a single calculation or value, using a plain expression is usually clearer. There is no need to add template delimiters when the entire input is already SpEL syntax.

## Distinguishing #{...} from property placeholders

In Spring configuration, two notation forms easily confused are **#{...}** and **dollar-brace placeholders**:

- **#{...}** is the delimiter commonly used to embed SpEL expressions in integration points that support SpEL.
- **dollar-brace placeholder** is the syntax for retrieving values from configuration sources such as properties or Environment.

Example:

~~~java
@Value("${app.name:Demo}")
private String applicationName;

@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

Field **applicationName** retrieves the **app.name** property and uses **Demo** as the default value when the property is not declared. Field **timeZone** evaluates a SpEL expression to read the system property **user.timezone**.

The two mechanisms solve two different tasks. Property placeholders substitute configuration values; SpEL evaluates expressions against data and an EvaluationContext. Some Spring integration points can coordinate both mechanisms, but the plain parser API does not automatically treat a placeholder as a SpEL expression.

Also distinguish a template expression parsed directly with **TemplateParserContext** from how an annotation or Spring integration processes **#{...}**. When using the parser API, explicitly pass ParserContext if the string has static text outside the expression segments.

## Text-only or expression-only templates

A template can contain multiple text and expression parts. If there is no static text, a plain expression is usually the more direct choice:

~~~java
Expression expression =
        parser.parseExpression("#total * 1.08");

BigDecimal totalWithTax =
        expression.getValue(context, BigDecimal.class);
~~~

If the result needs to be placed into a message sentence, a template is more suitable:

~~~java
Expression template = parser.parseExpression(
        "Total payment: #{#total * 1.08}",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

In the second example, the calculation is inside the embedded expression segment, while the label **Total payment: ** is static text. If the result needs currency formatting, locale handling, or business rounding, prepare the formatted value in Java instead of putting extensive formatting logic into the template.

## Reusing Expression and EvaluationContext

A template can be parsed once and evaluated multiple times with different contexts:

~~~java
Expression template = parser.parseExpression(
        "Hello, #{#name}!",
        new TemplateParserContext());

StandardEvaluationContext firstContext =
        new StandardEvaluationContext();
firstContext.setVariable("name", "An");

StandardEvaluationContext secondContext =
        new StandardEvaluationContext();
secondContext.setVariable("name", "Binh");

String first =
        template.getValue(firstContext, String.class);

String second =
        template.getValue(secondContext, String.class);
~~~

The same template structure can generate content for multiple recipients. Expression retains the parsed string; dynamic values come from the context at evaluation time.

If variables hold request-specific data, use a dedicated context for that request. Do not mutate variables on a mutable EvaluationContext shared concurrently by multiple threads, as concurrent evaluations may read each other's data.

## Delimiters and input text

When choosing template delimiters, ensure the open/close pair does not conflict with the surrounding text syntax. If using custom delimiters, every place that parses the template must use the same ParserContext.

In addition, static text and embedded expressions have different origins:

- Text outside delimiters is preserved as literal text.
- Content inside delimiters is evaluated as SpEL in the provided EvaluationContext.

If the entire template or part of a template comes from users, do not assume the content is merely display text. Users could place syntax inside the delimiter region to create expressions that get evaluated. Control who can edit templates and restrict the root object, variables, property accessors, method resolvers, and other context capabilities.

Template results are also not automatically escaped for HTML, SQL, shell, or a specific output format. When sending results to a UI or another system, apply encoding/escaping rules appropriate for the target.

## Parse errors and evaluation errors

Both plain expressions and template expressions can fail at two stages:

- **ParseException:** the string has invalid syntax, mismatched delimiters, an unsuitable ParserContext, or an embedded expression segment has invalid syntax.
- **EvaluationException:** the expression parsed successfully but cannot be evaluated with the current data or EvaluationContext, such as an unprovided variable, nonexistent property, or disallowed method call.

The two stages can be separated for clear handling:

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

If templates are stored in configuration, they can be parsed when loading configuration to catch syntax errors early. Evaluation still requires a valid root object, variables, and context at runtime.

Do not catch all evaluation errors and return an empty string without recording the cause. That can hide variable, property, or method errors and cause incorrect output to go unnoticed.

## When to choose each type?

Use a **plain expression** when:

- The entire input string is SpEL syntax.
- You need to compute, compare, or return a value.
- The expression is used as a condition or configuration value.
- The result can be represented by a string literal or simple SpEL concatenation.

Use a **template expression** when:

- You need to mix ordinary text with dynamic data.
- You want to build messages or labels from multiple variables.
- There are multiple expression segments in the same string.
- You want to clearly separate fixed content from evaluated parts.

If only replacing a few property placeholders, using the corresponding configuration mechanism is usually more appropriate. If you need templates with localization, complex formatting, loops, or many branches, consider a dedicated template engine or building the content in Java.

## Conclusion

A **plain expression** treats the entire string as SpEL syntax and typically uses **parseExpression(String)**. A **template expression** combines static text with SpEL segments marked by delimiters, using **parseExpression(String, ParserContext)**. **TemplateParserContext** defaults to prefix **#{** and suffix **}**, while also allowing custom delimiter pairs.

Use plain expressions for calculations and conditions; use templates when placing expression results inside ordinary text. Distinguish SpEL delimiters from property placeholders, pass the ParserContext matching the delimiters, and restrict the EvaluationContext if templates can be edited from external sources.
