# Templates Without Expressions and Corresponding Behavior

In Spring Expression Language (SpEL), template expressions allow combining static text with the results of expressions placed inside a delimiter pair. However, a template is not required to contain expressions. If the input string has no expression region, the parser in template mode treats the entire content as literal text, and the evaluation result preserves that content as-is.

This behavior is useful when a configuration source may contain both static strings and dynamic strings. The application can use the same template parsing mechanism for both cases: strings with expressions are evaluated, while strings without expressions are returned as the original text. Template mode must be distinguished from parsing a standard SpEL expression, because a plain text string does not automatically become a string literal in SpEL syntax.

## 1. What Is a Template Expression?

A template expression is a string that can contain two types of components:

- Literal text: the part preserved as-is in the result.
- Expression segment: the part between prefix and suffix, parsed and evaluated by SpEL.

With the default parser context for templates, the prefix is #{ and the suffix is }.

Example:

    Hello, #{#userName}!

In this string, Hello, and ! are literal text. The #userName part is an expression evaluated using data in EvaluationContext.

If the userName variable has the value An, the result is:

    Hello, An!

Template expressions are parsed using the overload accepting ParserContext:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "Hello, #{#userName}!",
            ParserContext.TEMPLATE_EXPRESSION);

ParserContext tells the parser that the string should be processed in template mode. If ParserContext is omitted, the parser treats the input as a normal SpEL expression and does not apply rules for combining literal text with #{...} regions.

## 2. How Are Templates Without Expressions Processed?

Suppose the input is just text:

    Welcome to Spring Framework.

There is no #{ prefix, so there is no expression segment to parse. When using the template parser context:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "Welcome to Spring Framework.",
            ParserContext.TEMPLATE_EXPRESSION);

    String result = expression.getValue(String.class);

The value of result is:

    Welcome to Spring Framework.

SpEL preserves the text content as-is. It does not look up properties, call methods, read variables in EvaluationContext, or need a root object to produce this result.

This is important behavior when an application processes templates supplied by configuration. A static string is still valid input for the template parser; there is no need to add an empty expression or a dummy expression just for the parser to accept the string.

## 3. A Literal-Only Template Is Not a SpEL String Literal

There are two different ways to instruct SpEL to return a static string.

The first way is to parse a string literal according to standard SpEL syntax. A string literal must be enclosed in single quotes:

    Expression expression =
            parser.parseExpression("'Welcome to Spring Framework.'");

The second way is to parse plain text in template mode:

    Expression expression =
            parser.parseExpression(
                    "Welcome to Spring Framework.",
                    ParserContext.TEMPLATE_EXPRESSION);

Both can return the same content, but their syntactic meaning differs:

| Input | Parser context | Meaning |
|---|---|---|
| 'Welcome' | Default | SpEL string literal |
| Welcome | Default | Identifier/property expression, not literal text |
| Welcome | Template | Template text preserved as-is |
| Hello #{#name} | Template | Literal text combined with expression |

Therefore, if the input is display content or configuration text, use a template parser context. If the input is genuinely a SpEL expression returning a string, use a string literal or string concatenation expression in SpEL syntax.

## 4. Complete Java Example for a Template Without Expressions

You can evaluate a text-only template without creating an EvaluationContext:

    ExpressionParser parser = new SpelExpressionParser();

    String templateText = "Order processing is enabled.";

    Expression expression = parser.parseExpression(
            templateText,
            ParserContext.TEMPLATE_EXPRESSION);

    String message = expression.getValue(String.class);

The result message equals templateText itself.

If the application already has an EvaluationContext used for other templates, you can pass the context into getValue:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

    String message = expression.getValue(
            context, String.class);

For a template without expressions, the context is not used to look up data because there are no expression segments to evaluate. Passing the context does not alter the literal text.

This allows a unified processing flow: parse templates using the same ParserContext, then evaluate with the appropriate context. Static strings do not need a special branch just to return their content.

## 5. Comparing Static Templates and Templates with Expressions

Consider three inputs:

    "Welcome to Spring."

    "Welcome, #{#userName}."

    "Order total: #{#order.total}"

When using ParserContext.TEMPLATE_EXPRESSION, the corresponding behavior is:

- The first template has no expressions, so it is returned verbatim.
- The second template replaces the #{#userName} region with the value of the userName variable.
- The third template reads total from the root object order and inserts the result into the literal text.

Evaluation example:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("userName", "An");

    ExpressionParser parser = new SpelExpressionParser();

    Expression staticTemplate = parser.parseExpression(
            "Welcome to Spring.",
            ParserContext.TEMPLATE_EXPRESSION);

    Expression namedTemplate = parser.parseExpression(
            "Welcome, #{#userName}.",
            ParserContext.TEMPLATE_EXPRESSION);

    Expression orderTemplate = parser.parseExpression(
            "Order total: #{total}",
            ParserContext.TEMPLATE_EXPRESSION);

    String first = staticTemplate.getValue(context, String.class);
    String second = namedTemplate.getValue(context, String.class);
    String third = orderTemplate.getValue(context, String.class);

The first result does not depend on order or userName. The second result depends on the userName variable. The third result depends on the total property of the root object.

## 6. No Expression Does Not Mean an Expression Returning an Empty String

Three cases should be distinguished:

1. Template without expression regions: the entire string is literal text.
2. Template with an expression returning an empty string: the expression region is evaluated and its result is an empty string.
3. Template with an expression returning null: the expression is still evaluated, but the return value is null and converting/concatenating the value into text must be handled according to the application's intent.

Literal-only template example:

    "Hello!"

Example with an expression returning an empty string:

    "Hello#{''}!"

Example actively using a fallback if a variable may be null or an empty string:

    "Hello #{#userName ?: 'Guest'}!"

Do not add an empty expression just to simulate the no-expression case. If you want to display a fixed string, leave the entire template as literal text. If you want a dynamic part with a replacement value, express the fallback directly inside the expression.

## 7. Templates Containing Only One Expression

A template can consist solely of an expression region without surrounding literal text:

    #{#order.total}

In this case, the result is determined by the inner expression. If the expression returns BigDecimal, Boolean, or another Java type, do not assume the result is always a String just because the input was parsed in template mode.

Example:

    Expression expression = parser.parseExpression(
            "#{#order.total}",
            ParserContext.TEMPLATE_EXPRESSION);

    BigDecimal total =
            expression.getValue(context, BigDecimal.class);

Conversely, when a template has literal text combined with expressions, the result is concatenated into a string:

    "Total: #{#order.total}"

If the application's API requires a String, design the template with literal text or explicitly convert the expression result to a string type. Choosing the target type in getValue should accurately reflect the actual type returned by the expression.

## 8. Using TemplateParserContext Explicitly

Instead of using the ParserContext.TEMPLATE_EXPRESSION constant, you can instantiate TemplateParserContext:

    ParserContext templateContext =
            new TemplateParserContext();

    Expression expression = parser.parseExpression(
            "Welcome to Spring.",
            templateContext);

The default constructor uses prefix #{ and suffix }. This style is useful when you want to keep ParserContext as a named configuration object reused across multiple places.

You can create TemplateParserContext with custom delimiters:

    ParserContext customContext =
            new TemplateParserContext("[[", "]]");

    Expression expression = parser.parseExpression(
            "Welcome, [[#userName]].",
            customContext);

In the example, [[ opens the expression segment and ]] closes it. The remaining part stays literal text. Customizing delimiters avoids conflicts when template sources already use #{...} for another text purpose.

Delimiters must be consistent between where templates are created and where they are parsed. If templates are stored in a database or configuration file, document the delimiter syntax clearly so editors know which regions will be executed as SpEL.

## 9. Text Containing Delimiter-Like Symbols

A string might need to display the #{ symbol as ordinary text, such as when documentation describes template syntax. If the parser is using prefix #{, that symbol may be interpreted as the start of an expression.

Do not assume all parser contexts support the same escaping rule for delimiters. If content must contain literal delimiters verbatim, you can choose a custom delimiter pair that does not appear in the content, or concatenate literal text in Java after evaluating the dynamic parts.

Example choosing different delimiters:

    ParserContext context =
            new TemplateParserContext("[[", "]]");

    Expression expression = parser.parseExpression(
            "Syntax marker #{name}; user is [[#userName]].",
            context);

In this example, #{name} is kept as literal text because the parser only recognizes [[ and ]] as expression delimiters.

If escaping must be supported via a custom convention, define and test that convention in the application's template processing layer. Do not leave template authors guessing how the parser handles delimiters appearing in content.

## 10. Delimiter Errors and Empty Expressions

A template without expressions is valid, yet an opened expression segment must have valid structure.

Example:

    "Welcome to Spring."

is a literal-only template and needs no delimiters.

Meanwhile:

    "Welcome, #{#userName"

has a prefix without a closing suffix. The parser cannot determine the expression boundary and will report a parse error.

Similarly:

    "Welcome, #{}"

has an empty expression region. This is not the way to state "no expression"; remove the delimiters altogether if you want the entire content to be literal.

When receiving an error, check the following points:

- Whether a prefix appears while the corresponding suffix is missing.
- Whether the expression inside delimiters is empty or syntactically invalid.
- Whether the delimiters configured at parse time match the delimiters used in the template.
- Whether quotes, parentheses, or delimiter characters inside the expression are properly closed.

## 11. Literal-Only Templates and Evaluation Cost

When a template contains no expressions, SpEL does not need to look up root properties, variables, beans, or invoke methods to produce the result. The input content is used as literal text.

Even so, if the application parses the same template multiple times, there is still repeated Expression creation overhead. For fixed templates or rarely changing configurations, you can parse once and reuse the Expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression messageTemplate = parser.parseExpression(
            "The service is ready.",
            ParserContext.TEMPLATE_EXPRESSION);

    String message = messageTemplate.getValue(String.class);

If template content changes according to configuration, re-parse when configuration is loaded or updated, rather than parsing unnecessarily on every request.

Do not cache Expressions under an overly generic key if templates have different delimiters or parser configurations. Tie the cache key to both the content and the corresponding parser configuration.

## 12. Using Templates in Spring Applications

Template parser context is a SpEL API. It does not automatically take effect for every string in the application. Callers must actively parse strings using an ExpressionParser along with a template ParserContext.

Example of a service evaluating notification templates:

    public class MessageTemplateService {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        private final ParserContext templateContext =
                ParserContext.TEMPLATE_EXPRESSION;

        public String render(
                String template, EvaluationContext context) {

            Expression expression =
                    parser.parseExpression(
                            template, templateContext);

            return expression.getValue(context, String.class);
        }
    }

With input Service is ready., the result is that same string. With input Hello, #{#userName}!, the userName variable is evaluated against the passed-in context.

If templates can come from users or administrators, restrict the context and capabilities that expressions are allowed to use. A template without expressions only returns text, whereas another template with delimiters can invoke properties, methods, or capabilities provided by the context. Do not treat every template from the same source as having equal trust level.

## 13. Testing Behavior of Templates Without Expressions

Write dedicated tests for literal-only templates to ensure the parser context is used properly and content is not unintentionally altered.

Cases to test:

- Normal string without delimiters: result equals the exact input string.
- Empty string: result is an empty string.
- String with leading/trailing spaces: spaces are preserved.
- Multi-line string: line breaks and line order are preserved.
- String with valid delimiters: expression segments are evaluated.
- String with prefix but no suffix: parser reports an error.
- String with empty expression: parser reports an error rather than treating it as a no-expression template.
- Template with only one expression: result type follows that expression.
- Template mixing literal and expression: result is concatenated in exact order.

Simple test example:

    @Test
    void returnsLiteralTextWhenTemplateHasNoExpression() {
        ExpressionParser parser =
                new SpelExpressionParser();

        Expression expression = parser.parseExpression(
                "  Service is ready.  ",
                ParserContext.TEMPLATE_EXPRESSION);

        String result = expression.getValue(String.class);

        assertEquals("  Service is ready.  ", result);
    }

This test verifies that both content and whitespace are preserved. If a template is display data, accidentally trimming or normalizing it can alter the formatting intended by the configurator.

## 14. Common Misconceptions

| Situation | Cause | How to handle |
|---|---|---|
| Plain text interpreted as a property | Used default parseExpression(String) | Pass ParserContext.TEMPLATE_EXPRESSION |
| Template without expressions treated as missing data | Thinking every template must contain #{...} | Accept literal-only templates and use the returned content |
| Using #{} to represent no expression | Confusing an empty expression with no segment | Remove delimiters, keep literal text |
| Template with prefix but missing suffix | Unclosed expression segment | Fix delimiters or reject invalid template |
| Result of expression-only template is not String | Expression returns its original type | Choose an appropriate getValue type or convert explicitly |
| Symbol #{ in content gets parsed | Overlaps with configured prefix | Use custom delimiters or concatenate literals in Java |
| Changed delimiters while parser still uses old config | TemplateParserContext does not match template | Use the same ParserContext at parse time |

## Conclusion

A SpEL template without expressions is still valid input. When parsed with ParserContext.TEMPLATE_EXPRESSION or TemplateParserContext, the entire string is treated as literal text and the evaluation result preserves that content. No root object, variables, or methods are needed to handle this case.

Distinguish literal-only templates from SpEL string literals and from templates whose expression returns an empty string. Use an explicit parser context, keep delimiters consistent, validate templates for unbalanced prefix/suffix pairs, and choose the appropriate result type. If a template can contain expressions provided by others, restrict EvaluationContext according to the use case and trust level of the template source.