# Escaping Delimiters and Text Containing Special Symbols

## Objectives

Spring Expression Language (SpEL) supports **template expressions**: a string can mix static text with one or more expression blocks evaluated at runtime. By default, an expression block starts with **#{** and ends with **}**. This syntax is convenient for creating messages, labels, configuration content, or strings with dynamic data.

Difficulty arises when the text to be displayed also contains symbols resembling delimiters, such as documentation strings with **#{name}** examples, JSON with curly braces, or text with many special characters. You need to distinguish template delimiters from characters inside a SpEL expression and from Java string escaping when constructing strings.

After this lesson, you will be able to:

- Parse a template using TemplateParserContext.
- Mix static text with multiple expression blocks.
- Use default delimiters or configure custom delimiters.
- Preserve delimiter-like strings in template output.
- Understand the role of string literals and brackets when the parser searches for the closing point.
- Distinguish Java string escaping from template delimiter recognition.
- Diagnose missing delimiter errors, empty expressions, and unbalanced brackets.

## 1. What Is a Template Expression?

A template expression is a string consisting of static text segments interspersed with SpEL blocks marked by a prefix and suffix. The parser evaluates each block and concatenates the results with the static text segments in exact order.

With default delimiters, for example:

~~~text
Hello, #{#name}!
~~~

If the name variable has the value Lan, the result is:

~~~text
Hello, Lan!
~~~

The Hello, part and the ! mark are static text. The #{#name} block is the evaluated expression.

A template differs from a standard SpEL expression. When calling parseExpression(expressionString) without passing a ParserContext, the parser treats the entire string as an expression. When you want to mix static text with expression blocks, you need to pass a ParserContext whose isTemplate() returns true.

## 2. Default Delimiters and TemplateParserContext

TemplateParserContext is the ParserContext implementation used for template parsing. The default constructor uses:

- Prefix: **#{**
- Suffix: **}**

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");

Expression expression = parser.parseExpression(
    "Hello, #{#name}!",
    new TemplateParserContext()
);

String result = expression.getValue(context, String.class);
~~~

The result is Hello, Lan!.

You can use ParserContext.TEMPLATE_EXPRESSION instead of a default TemplateParserContext:

~~~java
Expression expression = parser.parseExpression(
    "Hello, #{#name}!",
    ParserContext.TEMPLATE_EXPRESSION
);
~~~

Both approaches tell the parser to process the string in template mode with the default prefix and suffix.

If the application uses the same delimiters in multiple places, standardize how ParserContext is created to avoid one template being parsed in a different mode from the rest.

## 3. Mixing Multiple Text Segments and Multiple Expressions

A template can contain multiple expression blocks:

~~~text
Order #{#orderId} for #{#customerName} has total #{#total}.
~~~

With the corresponding variables in the context, the parser evaluates each block and concatenates the results in their original order.

Example:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("orderId", "ORD-1024");
context.setVariable("customerName", "Lan");
context.setVariable("total", new BigDecimal("250.00"));

Expression expression = parser.parseExpression(
    "Order #{#orderId} for #{#customerName} has total #{#total}.",
    new TemplateParserContext()
);

String message = expression.getValue(context, String.class);
~~~

Templates keep formatting in a single string while data is passed via variables. When content has many dynamic segments, this is easier to read than manual string concatenation in Java.

The result of each expression block is placed into the output string. Therefore, determine the return data type and its representation. For currency, dates, or numbers requiring locale formatting, format values explicitly beforehand or use a dedicated function rather than relying on an object's default representation.

## 4. Static Text and Expression Blocks

The parser recognizes the prefix in the template text. Segments outside expression blocks are kept as literal text. Segments inside delimiters are parsed as SpEL expressions.

Example:

~~~text
Status: #{#status}; retries: #{#retryCount}.
~~~

If status is ACTIVE and retryCount is 3, the output looks like:

~~~text
Status: ACTIVE; retries: 3.
~~~

Characters such as periods, commas, colons, hyphens, or square brackets in static text usually require no special handling if they do not form the template prefix.

A } suffix in static text also does not start an expression block on its own. What requires the most attention with default delimiters is the **#{** prefix, since the parser uses it to find the start of an expression block.

## 5. Preserving Delimiters in Output Content

If the text to be displayed contains the **#{** prefix itself, the default parser will interpret it as the start of an expression block. Do not assume that adding a backslash before the prefix will always escape the delimiter; TemplateParserContext does not define a general backslash escaping rule for prefixes.

There are two common ways to preserve delimiter-like strings.

### Approach 1: Producing a String Literal from an Expression Block

You can use an expression block that returns the exact string to display:

~~~text
Syntax in documentation: #{'#{name}'}
~~~

Output result:

~~~text
Syntax in documentation: #{name}
~~~

The parser sees #{ at the start of the outer block. Inside, the string '#{name}' is a SpEL string literal, so the characters inside the string are preserved as data. The final } closes the outer expression block.

Similarly, to output the opening delimiter string:

~~~text
#{'#{'}
~~~

The result is:

~~~text
#{
~~~

And to output a closing curly brace:

~~~text
#{'}'}
~~~

The result is:

~~~text
}
~~~

This approach fits well when there are only a few places that need to display delimiters in the content.

### Approach 2: Using Custom Delimiters

If literal content frequently contains **#{** or needs to preserve many SpEL examples verbatim, choose a different delimiter pair for the template.

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
    "SpEL example: #{name}; actual name: [[#name]]",
    parserContext
);
~~~

With the name variable equal to Lan, the result is:

~~~text
SpEL example: #{name}; actual name: Lan
~~~

In this example, **[[** starts the expression block and **]]** closes the block. The string #{name} is no longer a template delimiter, so it is kept as static text.

Custom delimiters must be configured consistently everywhere the same template type is parsed. If templates are stored in a database or configuration file, store the delimiter convention alongside them or specify it via application configuration.

## 6. Distinguishing Template Escaping from Java String Escaping

There are two distinct stages when a template is written in Java code:

1. The Java compiler processes a string literal or text block to produce a String.
2. The SpEL parser reads that String and recognizes template delimiters.

Example:

~~~java
String template = "Hello, #{#name}!";
~~~

In this Java string, the characters #, {, and } do not need escaping under Java syntax. The SpEL parser receives the actual string and processes #{ as the template prefix.

If the content contains backslashes, double quotes, or control characters, Java string literal rules must be followed first. For Java text blocks, escaping rules also belong to the Java language. These escapes determine which characters are sent to SpEL; they do not automatically create a new delimiter escaping rule for TemplateParserContext.

Do not write a string with a backslash and assume SpEL will strip the backslash before the prefix. Inspect the actual Java string produced and choose one of the two approaches: represent the delimiter as a string literal inside an expression, or switch to custom template delimiters.

## 7. Brackets and String Literals Inside Expression Blocks

When searching for the suffix that closes an expression block, the parser must distinguish brackets used for expression structure from characters inside string literals.

Example:

~~~text
Message: #{'Value with a } brace inside the string'}
~~~

The } brace inside the string literal does not close the expression block. The } after the closing quote is the suffix that ends the block.

Similarly, expressions can contain balanced brackets:

~~~text
Result: #{T(java.lang.Math).max(10, 20)}
~~~

The parser tracks parentheses, square brackets, and curly braces to identify the matching suffix. Brackets inside a string literal are treated as string content, not expression structure.

If brackets are unbalanced or a string literal is unclosed, the parser may report an error before the expression is evaluated. Inspect each expression block individually when a template has multiple levels of brackets or complex strings.

## 8. Custom Delimiters and Custom ParserContext

TemplateParserContext allows passing prefix and suffix via its constructor:

~~~java
new TemplateParserContext("[[", "]]")
~~~

You can choose delimiters suited to the application's data format. For example, if text mostly contains SpEL #{...} syntax, [[...]] delimiters can reduce confusion.

If special parsing logic is needed, an application can implement ParserContext itself. This interface provides three pieces of information:

- isTemplate(): indicates whether the parser is processing a template.
- getExpressionPrefix(): returns the prefix opening an expression block.
- getExpressionSuffix(): returns the suffix closing an expression block.

ParserContext specifies how the parser recognizes templates. It does not by itself change the semantics of the SpEL expressions inside each block.

When defining custom delimiters, choose a symbol pair that rarely appears in literal text, is easy to recognize during code review, and does not conflict with the data format the template must hold.

## 9. Common Errors and How to Diagnose Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| Parser reports missing suffix | Opening prefix exists but no matching suffix is found | Check closing delimiter and brackets inside the block |
| Prefix in text is misparsed | Literal text contains the template's exact prefix | Use a string literal expression or custom delimiters |
| Empty expression block | Prefix is immediately followed by suffix with no expression | Remove the empty delimiter pair or provide a valid expression |
| A } inside a string confuses parsing | Unclosed string literal or unbalanced brackets | Check quotes and bracket structure |
| Template parsed as normal expression | Template ParserContext was not passed to parseExpression | Use TemplateParserContext or ParserContext.TEMPLATE_EXPRESSION |
| Custom delimiters do not work | Parse-time prefix/suffix differs from template creation delimiters | Use the same ParserContext configuration |
| Backslash does not escape prefix as expected | Confusing Java escaping with delimiter recognition | Inspect the actual String and choose an appropriate literal representation |
| Object display result has wrong format | Expression value is converted to text using default representation | Format data beforehand or use a formatting function |

Distinguish parse errors from evaluation errors. Parse errors involve delimiters, string literals, or expression syntax. Evaluation errors occur after the template has parsed, such as a missing variable, nonexistent property, or an invoked method throwing an exception.

## 10. Testing Templates and Delimiters

A test suite should verify literal parts, expression blocks, and custom delimiters.

Basic test example:

~~~java
@Test
void evaluatesTemplateWithLiteralAndExpression() {
    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();
    context.setVariable("name", "Lan");

    Expression expression = parser.parseExpression(
        "Hello, #{#name}!",
        new TemplateParserContext()
    );

    assertEquals("Hello, Lan!", expression.getValue(context, String.class));
}
~~~

Testing preservation of the prefix in output:

~~~java
@Test
void preservesTemplateDelimiterAsLiteralOutput() {
    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        "Syntax: #{'#{name}'}",
        new TemplateParserContext()
    );

    assertEquals("Syntax: #{name}", expression.getValue());
}
~~~

Testing custom delimiters:

~~~java
@Test
void usesCustomTemplateDelimiters() {
    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();
    context.setVariable("name", "Lan");

    ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

    Expression expression = parser.parseExpression(
        "Literal #{name}; value [[#name]]",
        parserContext
    );

    assertEquals(
        "Literal #{name}; value Lan",
        expression.getValue(context, String.class)
    );
}
~~~

Cases to test:

- Template with only static text.
- Template with one expression block.
- Template with multiple expression blocks.
- Prefix appearing as literal content that must be preserved.
- Suffix appearing inside a string literal.
- Parentheses, square brackets, and curly braces inside expressions.
- Empty expression block.
- Missing suffix or unclosed string literal.
- Custom prefix/suffix.
- Invalid variables or properties used in a block.
- Null values and result types requiring formatting.

## 11. Safety When Evaluating Templates

Template parsing still executes SpEL inside every expression block. Therefore, a template is not merely formatting text if the template author can insert arbitrary expressions.

If templates come from users or external sources:

- Do not allow users to freely add expression blocks if they are not permitted to execute SpEL.
- Separate user-supplied literal content from application-controlled expression code.
- Use an EvaluationContext with the minimum necessary access permissions.
- Only provide the root object, variables, functions, and resolvers that the template needs.
- Avoid letting expressions read sensitive data or call methods with side effects.
- Validate templates before saving or activating them.
- Limit template length and complexity according to application needs.

Changing delimiters only changes how the parser recognizes expression blocks. It is not a security mechanism and does not restrict what SpEL inside a block can do.

## 12. Process for Handling Templates with Special Symbols

When a template needs to contain symbols resembling delimiters:

1. **Identify current delimiters.** Note the exact prefix and suffix the parser is using.
2. **Classify each segment.** Determine which parts are literal text and which actually need evaluation.
3. **Preserve literal prefixes.** If #{ needs to be displayed, use an expression returning a string literal or choose different delimiters.
4. **Check strings and brackets.** Ensure quotes are closed, brackets are balanced, and suffixes sit in the right positions.
5. **Separate escaping by layer.** Check the Java string first, then check the string passed to SpEL.
6. **Parse with the right ParserContext.** Do not use the default parser context if the template was written with custom delimiters.
7. **Evaluate with the required context.** Provide complete variables and root object.
8. **Compare exact output.** Verify literal text, whitespace, brackets, and dynamic values.

If a template becomes complex enough to require escaping in many places, consider custom delimiters or splitting content into literal and expression segments managed separately in Java.

## 13. Best Practices

- Use TemplateParserContext when a string needs to mix literal text and SpEL expressions.
- Use default #{...} delimiters when there is no conflict with content.
- Use ParserContext.TEMPLATE_EXPRESSION if you want to use the built-in default template configuration.
- Choose custom delimiters when text frequently contains the default prefix.
- Use a string literal expression to output a few delimiter symbols verbatim.
- Do not assume backslash is a prefix escaping mechanism for TemplateParserContext.
- Distinguish Java string escaping from template delimiters.
- Keep expression blocks short and clearly purposed.
- Check quotes and bracket structure when special symbols are present.
- Format numbers, dates, and objects according to clear display rules.
- Use the same ParserContext configuration across parsing, testing, and production.
- Do not let untrusted templates execute SpEL with an overly broad context.

## 14. Review Checklist

Before putting a template into use, check:

- [ ] Is the string parsed in template mode?
- [ ] Are prefix and suffix clearly defined?
- [ ] Are literal text and expression blocks properly classified?
- [ ] Do blocks have valid, non-empty expressions?
- [ ] Are prefixes that need to appear verbatim handled intentionally?
- [ ] Is backslash not relied upon as an unconfigured delimiter escape?
- [ ] Are string literals and brackets inside blocks properly closed?
- [ ] Are custom delimiters used consistently everywhere?
- [ ] Is Java string escaping not confused with template parsing?
- [ ] Are dynamic values formatted according to display requirements?
- [ ] Do the template and EvaluationContext have trusted sources and appropriate permissions?
- [ ] Are there tests for literals, multiple blocks, special delimiters, and parse errors?

## Conclusion

SpEL template expressions combine static text with expression blocks delimited by a prefix and suffix. TemplateParserContext defaults to **#{** and **}**; the parser concatenates literal parts with the result of each block. When displayed content also contains the prefix, produce a string literal from an expression block or choose custom delimiters such as [[...]]. Do not confuse Java string escaping with template delimiter recognition, and do not assume a backslash can escape the prefix. Parse with the right ParserContext, verify quotes and brackets, and test exact output in a realistic EvaluationContext.

## References

- Spring Framework Reference — Expression Templating: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html
- Spring Framework API — TemplateParserContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html
- Spring Framework API — ParserContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParserContext.html