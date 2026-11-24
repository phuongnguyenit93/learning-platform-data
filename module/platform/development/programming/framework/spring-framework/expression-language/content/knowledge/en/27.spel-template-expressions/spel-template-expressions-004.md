# Resulting String When Multiple Expression Segments Are Present

In Spring Expression Language (SpEL), **template expressions** allow combining fixed text with multiple SpEL segments within the same string. When evaluated, Spring preserves the literal text, executes each expression segment, and concatenates the results into a complete string.

Example:

~~~text
Order #{#order.id} for customer #{#customer.name} has total #{#order.total}.
~~~

The result may look like:

~~~text
Order ORD-1024 for customer Linh has total 250.00.
~~~

This approach fits well when generating labels, messages, descriptions, configuration content, or display strings with multiple dynamic values. Instead of concatenating strings with multiple plus operators in Java or writing one long expression, you can place the dynamic parts right where they appear in the text.

## 1. What Is a Template Expression?

A template expression consists of two types of segments:

- **Literal text:** fixed text outside delimiters.
- **Embedded expression:** a SpEL segment between the prefix and suffix defined by ParserContext.

With default configuration, the delimiters are **#{** and **}**:

~~~text
Hello #{#user.name}, today is #{#today}.
~~~

The literal parts consist of "Hello ", ", today is ", and ".". The two parts inside delimiters are the expressions #user.name and #today.

When getValue() is called, SpEL evaluates the inner expressions and concatenates the results with the literal text into a single String.

A template can contain one, multiple, or no expression segments. If there are no dynamic parts, the result is simply the literal content. If there are multiple segments, each segment is evaluated while constructing the resulting string.

## 2. ParserContext and TemplateParserContext

To parse a template string, you must pass a **ParserContext** to ExpressionParser. ParserContext tells the parser that the input string is a template and which delimiters mark the expression parts.

Spring provides the **TemplateParserContext** implementation:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "Hello #{'Spring'}!",
        new TemplateParserContext()
);
~~~

The no-argument constructor of TemplateParserContext uses prefix **#{** and suffix **}**.

When calling:

~~~java
expression.getValue(String.class);
~~~

the result is:

~~~text
Hello Spring!
~~~

The key point is that you must use the parseExpression(expressionString, parserContext) overload. If you only call parseExpression(expressionString), the parser treats the entire string as a normal SpEL expression and does not automatically treat text outside #{...} as template literals.

### 2.1. ParserContext Only Controls Parsing

Two components should be distinguished:

- **ParserContext** determines whether the string is a template and which delimiters surround expressions.
- **EvaluationContext** provides the root object, variables, functions, property accessors, method resolvers, and bean resolver used when expressions are evaluated.

TemplateParserContext does not supply variables or beans on its own. If the template references #order or @priceFormatter, the context passed to getValue() must provide the corresponding data and resolution capabilities.

## 3. Building Strings with Multiple Expression Segments

Example with three dynamic parts in one sentence:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orderId", "ORD-1024");
context.setVariable("customerName", "Linh");
context.setVariable("total", new BigDecimal("250.00"));

Expression expression = parser.parseExpression(
        "Order #{#orderId} for #{#customerName} has total #{#total}.",
        new TemplateParserContext()
);

String message = expression.getValue(context, String.class);
~~~

Result:

~~~text
Order ORD-1024 for Linh has total 250.00.
~~~

Each #{...} segment is a separate expression parsed while analyzing the template. During evaluation, these segments share the passed-in EvaluationContext.

You can mix literals, property access, variables, calculations, and method calls:

~~~text
Hello #{#customer.name}, order #{#order.id}
has #{#order.items.size()} items and total amount #{#order.total * 1.08}.
~~~

The template preserves the wording, while SpEL handles the dynamic values.

## 4. Using Root Object and Variables in Templates

Template expressions can use a root object in the same way as regular SpEL expressions.

Example:

~~~java
Order order = ...;

Expression expression = parser.parseExpression(
        "Order #{id} for customer #{customer.name}",
        new TemplateParserContext()
);

String result = expression.getValue(order, String.class);
~~~

Here id and customer.name are read from the root object order.

If data is registered as variables, use the # sign:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("locale", "vi-VN");

Expression expression = parser.parseExpression(
        "Order code: #{#order.id}; locale: #{#locale}",
        new TemplateParserContext()
);

String result = expression.getValue(context, String.class);
~~~

Do not confuse root object properties with variables:

- id is a property of the root object when the root is Order.
- #order.id accesses the order variable and then reads its id property.
- @orderService is a bean reference and requires a BeanResolver.

## 5. Using Calculations and Methods in Each Segment

Each embedded expression can contain standard SpEL operators and syntax, as long as EvaluationContext supports the operation.

Example calculating total after tax:

~~~text
Subtotal: #{#order.subtotal}
Tax: #{#order.subtotal * #taxRate}
Grand total: #{#order.subtotal * (1 + #taxRate)}
~~~

Methods can be called on objects:

~~~text
Customer: #{#customer.getDisplayName()}
~~~

Or use property style if the class provides the corresponding getter:

~~~text
Customer: #{#customer.displayName}
~~~

If a method can cause side effects or call external systems, each template evaluation may trigger that action. For display strings, prefer expressions that read data or call pure methods with stable results.

### 5.1. Calling Registered Functions

If EvaluationContext has a normalizeCode function:

~~~text
Lookup code: #{#normalizeCode(#rawCode)}
~~~

The function is invoked during template evaluation, just as when used in a standalone expression.

### 5.2. Calling Methods on Spring Beans

If the context has a suitable BeanResolver:

~~~text
Formatted total: #{@priceFormatter.format(#order.total)}
~~~

The expression references the priceFormatter bean and calls the format method. When creating StandardEvaluationContext manually, you must configure BeanFactoryResolver; the template parser does not automatically look up beans in ApplicationContext.

## 6. Customizing Delimiters

You do not have to use #{ and }. You can create a TemplateParserContext with custom prefix and suffix:

~~~java
ParserContext parserContext =
        new TemplateParserContext("{{", "}}");

Expression expression = parser.parseExpression(
        "Hello {{#user.name}}!",
        parserContext
);
~~~

The template above uses {{ and }} to mark expression segments. When evaluated with a context containing the user variable, the result is a greeting string for the user.

Constructor syntax:

~~~java
new TemplateParserContext(expressionPrefix, expressionSuffix)
~~~

Prefix and suffix must be chosen as a pair suited to the template content. Another example:

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
        "Order [[#order.id]] is ready.",
        parserContext
);
~~~

Customizing delimiters is useful when literal strings frequently contain #{ or when an external system already uses its own syntax. Choose delimiters that do not conflict with fixed text so the parser recognizes boundaries clearly.

### 6.1. Custom ParserContext Implementation

ParserContext is an interface. If special template rules are needed, an application can implement this interface to provide:

- isTemplate(): indicates the input is a template.
- getExpressionPrefix(): returns the prefix opening an embedded expression.
- getExpressionSuffix(): returns the suffix closing an embedded expression.

In typical cases, TemplateParserContext already suffices and no custom implementation is required.

## 7. Distinguishing Template Expressions from String Concatenation with the Plus Operator

You can construct the same string using the plus operator:

~~~text
'Order ' + #order.id + ' for ' + #customer.name
~~~

Or using a template:

~~~text
Order #{#order.id} for #{#customer.name}
~~~

Both approaches produce the resulting string, but suit different writing styles:

| Criterion | Template expression | Plus operator |
| --- | --- | --- |
| Fixed text | Written directly outside delimiters | Must be placed inside string literals |
| Dynamic values | Placed at their positions in the sentence | Concatenated sequentially with the plus operator |
| Multiple dynamic segments | Easy to see the complete sentence layout | Expression can become long with many segments |
| Parser | Needs a template ParserContext | Parsed as a normal expression |
| Best suited for | Strings with many literal and dynamic parts | Short concatenations or computational expressions |

If only concatenating two values, the plus operator may be simpler. If the string has a lot of fixed wording interspersed with values, templates make the content easier to read and edit.

## 8. Template Expressions in @Value

Spring supports SpEL in the @Value annotation. You can combine literal text with expression parts:

~~~java
@Component
class RuntimeDescription {

    @Value("Application region: #{systemProperties['app.region']}")
    private String description;
}
~~~

During @Value processing, Spring evaluates the expression via the container's built-in mechanism and produces the resulting string.

Another example:

~~~java
@Value("Running on #{T(java.lang.System).getProperty('os.name')}")
private String runtimeLabel;
~~~

When using @Value, you do not need to call parseExpression() or create TemplateParserContext yourself. Spring processes annotation syntax according to its embedded value and expression resolver rules.

Distinguish property placeholders from SpEL:

~~~java
@Value("DOLLAR_OPEN{app.name:Spring Application}")
private String applicationName;
~~~

Placeholder DOLLAR_OPEN{...} reads configuration values and can supply defaults. SpEL #{...} evaluates expressions. The two mechanisms can be combined in Spring configuration, though each serves a distinct purpose.

## 9. Evaluation Timing and Reusing Expressions

parseExpression() creates an Expression object from a template string. Parsing does not mean dynamic values are fixed at parse time.

Embedded expressions are evaluated when getValue() is called:

~~~java
Expression expression = parser.parseExpression(
        "Hello #{#userName}!",
        new TemplateParserContext()
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("userName", "An");

String first = expression.getValue(context, String.class);

context.setVariable("userName", "Binh");

String second = expression.getValue(context, String.class);
~~~

The first evaluation produces Hello An!, and the second produces Hello Binh!. You can parse a template once and reuse the Expression with multiple EvaluationContexts or multiple input datasets.

This fits well when the same message template is used for many orders or users. Create a separate context per processing unit if evaluations need different variables, and avoid sharing a mutable context across concurrent requests.

## 10. Formatting Values in the Resulting String

Template expressions insert the results of embedded expressions into text. When an expression returns an object, the value is included in the string according to the String representation of the result.

Example with BigDecimal:

~~~text
Total amount: #{#order.total}
~~~

The output might show 250.00 according to BigDecimal's default representation. However, the default representation does not necessarily match UI or locale formatting rules.

If you need locale-aware formatting for currency, date/time, or decimals, call a dedicated formatter:

~~~text
Total amount: #{@priceFormatter.format(#order.total, #locale)}
Created date: #{@dateFormatter.format(#order.createdAt, #locale)}
~~~

Formatter beans must be resolvable in an EvaluationContext with a BeanResolver. Registered functions can be used if formatting is a static, standalone operation.

Do not place complex formatting rules repeatedly across multiple SpEL segments. A clearly named formatter standardizes results and is easier to test.

## 11. Handling Nulls and Errors in Embedded Expressions

Templates only concatenate results; they do not automatically validate all input data.

Example:

~~~text
Customer: #{#order.customer.name}
~~~

If order or customer is null, property access can fail. Use safe navigation at steps that may be null:

~~~text
Customer: #{#order?.customer?.name}
~~~

You can provide a default value using Elvis:

~~~text
Customer: #{#order?.customer?.name ?: 'Guest customer'}
~~~

If an embedded expression calls a method and the method throws an exception, evaluating the entire template may fail. Existing literal segments do not turn that error into a default string automatically.

Handle nulls and errors according to business rules. If a value is mandatory, validate the data beforehand or let the error be reported clearly rather than hiding it behind a generic fallback string.

## 12. Evaluation Order and Side Effects

Literal parts are preserved; embedded expressions are evaluated to construct the result string in the order they appear in the template.

Example:

~~~text
#{#firstStep()} - #{#secondStep()}
~~~

If both functions have side effects, the call order can affect application state. This is why template expressions should not be used to orchestrate business operations.

A display template should focus on reading and formatting data. Perform state updates, send notifications, or write data in a Java service with clear control flow, and then build the string from the results.

In addition, every call to getValue() re-evaluates the expression parts. If a template is used multiple times, methods inside the template may also be invoked multiple times. Do not assume dynamic results are cached just because the Expression was parsed once.

## 13. Common Errors When Parsing Templates

### 13.1. Forgetting to Pass ParserContext

Wrong:

~~~java
parser.parseExpression("Hello #{#user.name}!");
~~~

This tells the parser to treat the entire string as a regular expression.

Right:

~~~java
parser.parseExpression(
        "Hello #{#user.name}!",
        new TemplateParserContext()
);
~~~

### 13.2. Missing Suffix or Unbalanced Delimiters

If a template has an opening prefix without a corresponding suffix, the parser cannot determine the boundary of the embedded expression and may throw ParseException.

Incomplete example:

~~~text
Hello #{#user.name
~~~

Check each prefix/suffix pair and ensure expression content sits inside the chosen delimiters.

### 13.3. Using Mismatched Delimiters

If you create TemplateParserContext with {{ and }}, yet the template still uses #{...}, that segment is not recognized as an embedded expression under the new parser context.

ParserContext and the template string must use the same delimiter pair.

### 13.4. Confusing SpEL Syntax with Configuration Placeholders

Spring configuration placeholders and SpEL template delimiters serve different purposes. In configuration, ${...} is typically used to fetch properties; #{...} is used to evaluate SpEL.

If a string contains both mechanisms, check the processing order of embedded values and expressions at the specific integration point, such as @Value. Do not change delimiters arbitrarily as it can alter configuration semantics.

### 13.5. Placing Quotes Incorrectly in Expressions

String literals inside SpEL are usually enclosed in single quotes:

~~~text
Hello #{'Spring Framework'}!
~~~

If an expression needs a string containing a single quote, escape it according to SpEL literal syntax. Distinguish quotes wrapping a literal from quotes belonging to the data content itself.

## 14. Template Expressions Do Not Replace a Template Engine

SpEL template expressions are suitable for combining text and dynamic values in Spring configurations. They are not a general-purpose template engine for long documents.

If you need loops, complex conditional rendering, layouts, HTML escaping, localization, or template management for content authors, consider a dedicated template engine or MessageSource.

Some selection guidelines:

- Use SpEL templates for short configuration strings, labels, simple messages, and values produced at Spring integration points.
- Use MessageSource when managing multilingual messages is required.
- Use a template engine when document structure, loops, conditions, and escaping are needed.
- Use a Java service when content generation involves business logic or multiple processing steps.

## 15. Testing Template Expressions

Multiple expression segments can be tested with JUnit:

~~~java
class TemplateExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void combinesLiteralAndMultipleExpressions() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("orderId", "ORD-1024");
        context.setVariable("customerName", "Linh");
        context.setVariable("total", new BigDecimal("250.00"));

        Expression expression = parser.parseExpression(
                "Order #{#orderId} for #{#customerName}: #{#total}",
                new TemplateParserContext()
        );

        String result = expression.getValue(context, String.class);

        assertEquals(
                "Order ORD-1024 for Linh: 250.00",
                result
        );
    }

    @Test
    void reusesExpressionWithDifferentContexts() {
        Expression expression = parser.parseExpression(
                "Hello #{#name}!",
                new TemplateParserContext()
        );

        StandardEvaluationContext first =
                new StandardEvaluationContext();
        first.setVariable("name", "An");

        StandardEvaluationContext second =
                new StandardEvaluationContext();
        second.setVariable("name", "Binh");

        assertEquals("Hello An!", expression.getValue(first, String.class));
        assertEquals("Hello Binh!", expression.getValue(second, String.class));
    }
}
~~~

The first test verifies that literal text and multiple embedded expressions are combined properly. The second test verifies that a parsed Expression can be evaluated with different contexts.

Add tests for custom delimiters, missing variables, null properties, methods throwing exceptions, and templates missing a suffix if the application receives templates from external configuration.

## 16. Quick Recap

- Template expressions combine literal text and multiple embedded SpEL expressions in a single string.
- Default delimiters of TemplateParserContext are **#{** and **}**.
- Parse templates with **parseExpression(template, new TemplateParserContext())**.
- Each embedded expression segment is evaluated when getValue() is called; parsing once does not freeze dynamic values.
- Multiple expression segments in the same template share the passed-in EvaluationContext.
- Root properties, variables, functions, and bean references can be used if the context grants corresponding access.
- Create custom delimiters with **new TemplateParserContext(prefix, suffix)** when needed to avoid conflicts with literal content.
- ParserContext controls how parsing works; EvaluationContext controls data and access permissions during evaluation.
- Use safe navigation and Elvis when intermediate data may be null.
- Use dedicated formatters for currency, date/time, and locale.
- Minimize side effects in embedded expressions because each getValue() call re-evaluates dynamic segments.
- Use template expressions for short strings; use MessageSource or a template engine for content needing localization and complex structure.

## 17. Official References

- [Spring Framework — Language Reference and Template Expressions](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — ExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionParser.html)
- [Spring Framework — ParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParserContext.html)
- [Spring Framework — TemplateParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html)
- [Spring Framework — Expression and EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
