# SpEL Templates in Messages, Annotations, and Configuration

## Objectives

After this lesson, you will be able to distinguish standard SpEL expressions from template expressions; use TemplateParserContext to mix fixed text and evaluated expression segments; embed templates into Java messages, annotations, and Spring configuration; distinguish ${...} placeholders from SpEL #{...} expressions; and control data and access permissions in EvaluationContext. You will also learn how to handle delimiters, nulls, parse/runtime errors, and templates from untrusted sources.

## 1. What Is a Template Expression?

A standard SpEL expression describes the entire content to be evaluated:

~~~text
#customer.name
~~~

When evaluated, the result is the name property of the customer object.

A template expression allows mixing ordinary text with SpEL segments placed between a delimiter pair. With default delimiters, the expression part is placed between `#{` and `}`:

~~~text
Hello, #{#customer.name}!
~~~

The Hello, text and exclamation mark are preserved as-is. SpEL evaluates only the `#customer.name` segment and inserts the result at the right position.

Template expressions fit order notifications, emails, display labels, configuration messages, or strings injected into beans. Text outside delimiters is literal, not SpEL code.

## 2. Distinguishing Regular Expressions from Template Expressions

When parsing a string without passing a ParserContext, SpEL treats the entire string as an expression by default:

~~~java
Expression expression =
    parser.parseExpression("#customer.name");
~~~

When you need to mix text with SpEL segments, pass TemplateParserContext:

~~~java
Expression expression = parser.parseExpression(
    "Hello, #{#customer.name}!",
    new TemplateParserContext()
);
~~~

| Content | How to parse | Meaning |
|---|---|---|
| `#customer.name` | parseExpression(text) | Entire string is a single expression |
| `Hello, #{#customer.name}!` | parseExpression(text, new TemplateParserContext()) | Literal text interspersed with expression |
| `#{#customer.name}` | parseExpression(text, new TemplateParserContext()) | Template containing only one expression segment |

If you pass a free-form sentence to the parser without a template ParserContext, the parser may report an error because it tries to parse the whole sentence as SpEL.

## 3. TemplateParserContext and Default Delimiters

TemplateParserContext belongs to the org.springframework.expression.common package. The no-argument constructor uses default delimiters:

- Prefix: `#{`
- Suffix: `}`

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Order #{#orderId} is now #{#status}.",
    templateContext
);
~~~

TemplateParserContext tells the parser that the string is in template mode and identifies which parts are expressions. It does not supply variables, beans, or objects for evaluation; that data belongs to EvaluationContext.

You can use ParserContext.TEMPLATE_EXPRESSION if the Spring version in use provides this constant. Using new TemplateParserContext() makes the default delimiters explicit.

## 4. Complete Example: Creating Messages in Java

The following example creates a notification from a customer's name and order ID:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class MessageTemplateExample {

    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();

        String template =
            "Hello #{#customerName}, order #{#orderId} is #{#status}.";

        Expression expression = parser.parseExpression(
            template,
            new TemplateParserContext()
        );

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("customerName", "An");
        context.setVariable("orderId", "ORD-1024");
        context.setVariable("status", "SHIPPED");

        String message = expression.getValue(context, String.class);
        System.out.println(message);
    }
}
~~~

Result:

~~~text
Hello An, order ORD-1024 is SHIPPED.
~~~

The workflow has four steps: write the template string; parse with TemplateParserContext; register data in EvaluationContext; call getValue to produce the complete content.

You can parse a template once and reuse the Expression for multiple messages. On each evaluation, supply a context with data for the corresponding recipient or event.

## 5. Using Root Object Properties in Templates

Not every dynamic value needs to be a variable. Templates can read properties from the root object:

~~~text
Dear #{name}, your order #{order.id} is ready.
~~~

Java example:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

Expression expression = parser.parseExpression(
    "Order #{id} for #{customer.name} is ready.",
    new TemplateParserContext()
);

String message = expression.getValue(context, String.class);
~~~

Here id and customer.name are read from the root object order. If you want to reference an object registered as a variable, use the # sign:

~~~text
Order #{#order.id} for #{#order.customer.name} is ready.
~~~

Properties without a # prefix are read from the current evaluation object; variables with a # prefix are looked up in EvaluationContext.

If an intermediate property may be null, use safe navigation at each appropriate step:

~~~text
Hello #{#order?.customer?.name ?: 'customer'}!
~~~

Safe navigation guards access on null references; Elvis provides a fallback value. It does not fix data or create missing objects.

## 6. Multiple SpEL Segments in the Same Template

A template can contain multiple expression segments:

~~~text
Customer #{#customer.name} placed order #{#order.id} for #{#order.total}.
~~~

Each segment is evaluated in the same EvaluationContext. You can combine properties, variables, arithmetic operators, and conditions:

~~~text
Subtotal: #{#order.subtotal}
Tax: #{#order.subtotal * #taxRate}
Total: #{#order.subtotal * (1 + #taxRate)}
~~~

Example using the conditional operator:

~~~text
Payment: #{#order.paid ? 'received' : 'pending'}
~~~

Each expression part is evaluated and converted into content in the resulting string. Literal parts between segments are kept in exact order. Keep each SpEL segment short and easy to test.

## 7. Templates in the @Value Annotation

In a Spring application, @Value can inject values into fields, constructors, or setters.

Example injecting an expression value:

~~~java
@Component
public class RuntimeInfo {

    private final String region;

    public RuntimeInfo(
            @Value("#{systemProperties['user.region']}")
            String region) {
        this.region = region;
    }
}
~~~

Expressions can be used inside a string with literal text:

~~~java
@Component
public class GreetingConfig {

    private final String greeting;

    public GreetingConfig(
            @Value("Welcome, #{systemProperties['user.name']}!")
            String greeting) {
        this.greeting = greeting;
    }
}
~~~

Spring processes the string through the container's embedded value and bean expression resolution mechanism. Expressions are evaluated when Spring creates and injects beans according to the corresponding lifecycle.

@Value only works when the object is managed by Spring and the required post-processors are registered. If an object is created manually with new in Java, the annotation is not processed automatically.

Injected values are typically determined during bean initialization. If you need to generate a new message per request or recipient, use a template rendering service with its own context rather than treating a @Value field as a per-request dynamic message.

## 8. Templates in XML or Bean Definitions

SpEL can appear in bean configuration values, such as constructor arguments:

~~~xml
<bean id="messageProvider" class="com.example.MessageProvider">
    <constructor-arg
        value="Welcome, #{systemProperties['user.name']}!" />
</bean>
~~~

The Spring bean expression resolver can evaluate SpEL segments inside bean definition values. Remaining literal text is preserved in the resulting string.

Expressions can be used to calculate configuration values:

~~~xml
<property name="timeoutSeconds" value="#{30 * 2}" />
~~~

When writing XML, pay attention to XML escaping rules outside SpEL. For instance, the & character in an attribute must be written according to valid XML syntax. Quotes inside an expression should be chosen so they do not conflict with the quotes enclosing the attribute.

## 9. Distinguishing ${...} Placeholders from SpEL #{...}

Spring uses two common syntaxes with different purposes:

- `${...}` is a placeholder for retrieving values from property sources, such as application.properties, environment, or external configuration.
- `#{...}` is a SpEL expression evaluated in an EvaluationContext.

Placeholder example:

~~~java
@Value("${app.mail.sender}")
private String sender;
~~~

Spring fetches the configuration value named app.mail.sender.

SpEL example:

~~~java
@Value("#{systemProperties['user.name']}")
private String userName;
~~~

Spring evaluates an expression accessing a system property.

Placeholders and SpEL can be combined when embedded value resolution is properly configured:

~~~java
@Value("#{${app.tax-rate} * 100}")
private double taxPercent;
~~~

If app.tax-rate has value 0.08, the placeholder is replaced with 0.08 and then the SpEL part computes the result 8.0.

Do not confuse the two syntaxes: placeholders substitute configuration values; SpEL executes expressions. Placeholders do not on their own provide operators, method invocation, or object access like SpEL.

## 10. TemplateParserContext with Custom Delimiters

If text frequently contains literal `#{` and `}` strings, you can choose different delimiters.

Example using `[[` and `]]`:

~~~java
ParserContext customTemplateContext =
    new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
    "Welcome [[#name]]!",
    customTemplateContext
);
~~~

When evaluated, SpEL only treats what lies between [[ and ]] as an expression. Default delimiters #{ and } in the content are preserved as text since they are not this ParserContext's delimiters.

Custom delimiters are useful when templates have a system-specific syntax or content often contains curly braces. Choose a prefix and suffix that rarely appear in natural text, documentation, or user data.

ParserContext only controls how the parser splits the template. It does not reduce expression privileges and does not change how EvaluationContext resolves properties, methods, beans, or functions.

## 11. Delimiters Appearing in Literal Content

Template delimiters are used to identify SpEL segments. If a message needs to display an exact string resembling the prefix or suffix, consider:

- Using custom delimiters with fewer conflicts.
- Separating special literal parts and concatenating them into the message in Java.
- Avoiding creating templates by concatenating arbitrary data into expression strings.
- Testing with the exact parser context and Spring version being run.

Do not assume every delimiter character has the same escaping rule across all versions or parser contexts. If the application needs a custom escape mechanism, define and test that rule rather than adding backslashes by guesswork.

For complex templates with many nested syntaxes, a Java message builder or dedicated template engine may be easier to maintain.

## 12. Null Values and Expression Results

A SpEL segment in a template can return null. Decide clearly how the message should represent that case.

Example using Elvis:

~~~text
Hello #{#customer?.name ?: 'Guest'}!
~~~

If customer or name is null, the message uses Guest.

If null has a specific meaning, use an explicit condition:

~~~text
Status: #{#order.status == null ? 'not assigned' : #order.status}
~~~

Intermediate null properties also need handling:

~~~text
Delivery city: #{#order?.deliveryAddress?.city ?: 'not provided'}
~~~

Safe navigation only protects the steps where ?. is placed. If a property or getter throws an error for another reason, the template can still fail.

If a template uses multiple mandatory values, validate the context before evaluating. A message should not silently hide missing data if that data is required to send an accurate notification.

## 13. Result Types and Display Formatting

Template expressions usually produce a complete string because literal text is combined with dynamic values. Even if sub-expressions return numbers, dates, or objects, the application still needs to decide how to display them.

Example:

~~~text
Total: #{#order.total}
Created: #{#order.createdAt}
~~~

The displayed output depends on the value's string representation. For currency, date/time, or decimals, do not rely on default toString() if the message requires locale-based formatting.

You can prepare formatted strings in Java and pass them via variables:

~~~java
context.setVariable("formattedTotal", moneyFormatter.format(order.getTotal()));
context.setVariable("formattedDate", dateFormatter.format(order.getCreatedAt()));
~~~

Template:

~~~text
Total: #{#formattedTotal}
Created: #{#formattedDate}
~~~

This separates formatting logic from sentence structure and standardizes locale, timezone, currency unit, and rounding rules.

## 14. Parse Once, Evaluate Multiple Times

If the same template is used repeatedly, parse it once and reuse the Expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression messageTemplate = parser.parseExpression(
    "Hello #{#name}, order #{#orderId} is ready.",
    new TemplateParserContext()
);
~~~

Each time a message is generated, provide data in an appropriate context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");
context.setVariable("orderId", "ORD-1001");

String first = messageTemplate.getValue(context, String.class);

context.setVariable("name", "Binh");
context.setVariable("orderId", "ORD-1002");

String second = messageTemplate.getValue(context, String.class);
~~~

A parsed Expression can be reused with different values. However, do not share an EvaluationContext with mutable variables across multiple requests or threads without proper isolation.

A safe approach is to keep the template Expression shared while creating a separate context for each processing call or unit of work.

## 15. Distinguishing ParserContext and EvaluationContext

These two context types have different roles:

| Component | Responsibility | Example |
|---|---|---|
| ParserContext | Tells the parser the string is a template and defines delimiters | TemplateParserContext() |
| EvaluationContext | Provides root object, variables, and runtime access permissions | StandardEvaluationContext |
| TemplateParserContext | ParserContext implementing delimiters for templates | Prefix `#{`, suffix `}` |
| SimpleEvaluationContext | EvaluationContext with restricted access capabilities | Read-only data binding |

You can parse a template with TemplateParserContext and then evaluate it using an appropriate StandardEvaluationContext or SimpleEvaluationContext.

Changing ParserContext does not make expressions safer. To restrict permissions, choose the appropriate EvaluationContext and accessors/resolvers.

Conversely, choosing SimpleEvaluationContext does not automatically turn a text string into a template. The parser still needs a template ParserContext when the string has both literal text and SpEL segments.

## 16. Using SimpleEvaluationContext for Read-Only Templates

If a message only needs to read a few simple properties, you can use a read-only context:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression = parser.parseExpression(
    "Hello #{name}!",
    new TemplateParserContext()
);

String message =
    expression.getValue(context, customer, String.class);
~~~

This restricts property access to read-only data binding. It is well suited for templates needing to read data from a controlled object.

If a template needs to call methods, reference beans, types, or constructors, SimpleEvaluationContext may not support those capabilities under its current configuration. Only enable features that are truly required, and consider using Java to prepare data before rendering.

For templates coming from untrusted sources, do not use the default StandardEvaluationContext with broad permissions and allow users to write arbitrary SpEL.

## 17. Template Expressions in Messages and Emails

A message template typically has two parts:

- Sentence structure controlled by the application.
- Dynamic data obtained from a request, domain object, or context.

Example:

~~~text
Hello #{#customerName},

Your order #{#orderId} has been shipped.
Expected delivery: #{#deliveryDate}.
~~~

You can use the same template for many recipients by changing variables in EvaluationContext.

When generating HTML emails, handle output encoding. SpEL only evaluates expressions and concatenates strings; it does not automatically escape HTML, JavaScript, URLs, or content according to output context.

If customerName contains `<` characters or quotes, inserting it directly into HTML can break markup or create injection vulnerabilities. Encode data properly for the HTML text, attribute, or URL context using an appropriate library before placing it into the final content.

Do not use SpEL templates as a replacement for a template engine with auto-escaping when the application needs to render complex HTML.

## 18. Security When Templates Come from External Sources

Templates can contain SpEL expressions, so anyone with permission to edit templates can influence what gets evaluated.

Risk depends on EvaluationContext. With a broad context, expressions can access properties, invoke methods, reference beans, or use other capabilities if configured.

Security principles:

1. Only allow users authorized to manage templates to modify SpEL parts.
2. Treat templates as executable code, not plain text.
3. Pass data through variables rather than concatenating user data into expression strings.
4. Use dedicated root objects containing only data needed for display.
5. Prefer read-only EvaluationContexts and restrict accessors.
6. Do not expose services with side effects if the template only needs to read data.
7. Do not register beans, functions, or method resolvers broader than necessary.
8. Encode results according to the output context such as HTML or email.
9. Limit template length and expression count if users can author content.
10. Test templates before putting them into production.

ParserContext only separates literal text and expressions. It is not a sandbox and does not replace permission controls in EvaluationContext.

## 19. Parse Errors and Evaluation Errors

Two error groups must be distinguished.

**Parse errors** occur when the template or expression structure is invalid:

- Missing closing delimiter suffix.
- Inner expression has invalid syntax.
- Wrong ParserContext used.
- Unbalanced literals or quotes inside a SpEL segment.

**Evaluation errors** occur when parsing succeeds but execution fails with current data:

- Unregistered variable.
- Null root object or intermediate property.
- Nonexistent property.
- Method not permitted to be called.
- Bean reference missing a resolver or wrong bean name.
- Type conversion failure.
- Method or getter throwing an exception.

Parse templates when loading configuration or saving templates to catch syntax errors early. During rendering, handle evaluation errors against actual data and log the template identifier and cause while avoiding logging personal data or secrets.

Do not catch all errors and replace the entire message with an empty string without logging. That can drop important notifications with no trace for investigation.

## 20. Comprehensive Example: Templates in Application Configuration

Suppose application.properties contains:

~~~properties
app.tax-rate=0.08
app.message-prefix=Invoice
~~~

Values can be injected:

~~~java
@Component
public class InvoiceMessageConfig {

    private final double taxPercent;
    private final String prefix;

    public InvoiceMessageConfig(
            @Value("#{${app.tax-rate} * 100}") double taxPercent,
            @Value("${app.message-prefix}") String prefix) {
        this.taxPercent = taxPercent;
        this.prefix = prefix;
    }
}
~~~

In the example:

- `${app.tax-rate}` retrieves the value from the property source.
- `#{...}` instructs SpEL to compute on the substituted value.
- `${app.message-prefix}` fetches a plain configuration string without needing SpEL.

A separate message template can use the injected prefix:

~~~text
#{#prefix} #{#invoiceNumber}: total #{#formattedTotal}
~~~

The application registers prefix, invoiceNumber, and formattedTotal in the context before rendering. This separates application configuration, calculation expressions, and per-invoice data.

## 21. Testing Template Expressions

When testing, include:

| Case | What to verify |
|---|---|
| Literal text only | Content is preserved as-is |
| Single SpEL segment | Value is inserted at the right position |
| Multiple SpEL segments | All are evaluated in order |
| Variable | Value is read accurately from context |
| Root property | Property of root object is read accurately |
| Nested property | Intermediate objects are handled properly |
| Null | Safe navigation or default works as required |
| Custom delimiters | Only the chosen delimiters are recognized |
| Literal containing default delimiters | Not misinterpreted unintentionally |
| Placeholder ${...} | Resolved by property resolver |
| SpEL #{...} | Processed by parser/evaluator |
| Parse error | Detected prior to rendering |
| Evaluation error | Fails according to current data and permissions |
| HTML output | Data is encoded according to context |
| Concurrent requests | Context does not leak variables across requests |

Test both the final result and how ParserContext and EvaluationContext are configured. A template may parse successfully yet still fail when required variables or permissions are missing.

## 22. Key Takeaways

Template expressions allow mixing literal text with SpEL segments enclosed between delimiters. With default configuration, use TemplateParserContext to recognize `#{...}`. When parsing message strings containing ordinary text and expressions, pass a template ParserContext instead of treating the entire sentence as a SpEL expression.

TemplateParserContext determines how strings are split; EvaluationContext provides the root object, variables, and access permissions at evaluation time. Templates can be used in Java messages, @Value, and XML bean definitions. Placeholders `${...}` retrieve configuration values, while `#{...}` execute SpEL expressions; both syntaxes can work together when Spring's embedded value and expression resolution mechanisms are configured properly.

Use variables for dynamic data, keep template structure clear, handle nulls and errors separately, choose delimiters with minimal conflict, and encode results according to the output context. ParserContext is not a sandbox; templates from external sources require a least-privilege EvaluationContext and controlled data.

## References

- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [TemplateParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html)
- [ParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParserContext.html)
- [Spring @Value Annotation Reference](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)