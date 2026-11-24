# TemplateParserContext and Text Surrounding Expressions in SpEL

## Objective

`SpelExpressionParser` can parse a standalone SpEL expression, or parse a template string consisting of ordinary text interspersed with SpEL segments. The second case is useful when generating notifications, labels, email content, descriptive sentences, or display strings that have a few dynamic values.

`TemplateParserContext` tells the parser that the input string is a template and defines the start/end symbols of each expression segment. Parts outside those symbols are kept as literal text; parts inside are parsed and evaluated as normal SpEL.

## 1. Distinguishing standalone SpEL expressions and templates

When calling `parseExpression(expressionString)` without passing a `ParserContext`, the parser treats the entire string as one SpEL expression:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("customer.name");
```

Conversely, when passing `TemplateParserContext`, the string can contain both regular text and expression segments:

```java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression template = parser.parseExpression(
        "Hello #{customer.name}, your order has been received!",
        templateContext);
```

In this example, `Hello `, `, your order has been received!` are literal text. `customer.name` is the SpEL segment being evaluated. If `templateContext` is omitted, the parser will try to parse the entire sentence as a SpEL expression and parsing may fail.

## 2. Default delimiters of TemplateParserContext

The default constructor of `TemplateParserContext` uses:

| Component | Symbol | Role |
| --- | --- | --- |
| Expression prefix | `#{` | Marks the start point of a SpEL segment. |
| Expression suffix | `}` | Marks the end point of that SpEL segment. |

Example of a template with multiple expression segments:

```text
Hello #{customer.name}, order #{order.id} has a total amount of #{order.total}.
```

The parser processes each part in order:

1. Keep `Hello `.
2. Evaluate `customer.name`.
3. Keep `, order `.
4. Evaluate `order.id`.
5. Keep ` has a total amount of `.
6. Evaluate `order.total` and keep the trailing period.

When calling `getValue`, the literal parts and the results of the expression segments are concatenated into a single string. You can use the same template multiple times and evaluate it with an appropriate context on each call.

## 3. Complete example with a root object

Suppose the application has an `Order` with properties `id`, `customer.name`, and `total`. Set the order as the root object so that the properties in each `#{...}` segment are resolved from the order:

```java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Order order = orderService.findById(42L);
EvaluationContext evaluationContext = new StandardEvaluationContext(order);

Expression template = parser.parseExpression(
        "Order #{id} of #{customer.name} has a total amount of #{total}.",
        templateContext);

String message = template.getValue(evaluationContext, String.class);
```

The result has the following form (specific values depend on the order data):

```text
Order 42 of Lan has a total amount of 1250000.
```

The segments inside `#{...}` are syntactically independent SpEL expressions, so they can use properties, operators, method calls, or other SpEL features allowed by the evaluation context. The root object and variables in the context are shared when evaluating those segments.

## 4. Using variables in templates

You can pass per-request changing data into `EvaluationContext` using variables, then reference the variables with `#` inside the expression segment:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("currency", "VND");
context.setVariable("recipient", "Lan");

Expression template = parser.parseExpression(
        "Hello #{#recipient}, order #{id} has a total amount of #{total} #{#currency}.",
        new TemplateParserContext());

String message = template.getValue(context, String.class);
```

Here `id` and `total` are properties resolved from the root object `order`; `#recipient` and `#currency` are variables registered by the application. Using a template does not change SpEL's property or variable resolution rules.

## 5. Customizing delimiters

If the symbols `#{` and `}` conflict with template content or application conventions, pass a custom prefix and suffix to the constructor:

```java
ParserContext templateContext = new TemplateParserContext("${", "}");

Expression template = parser.parseExpression(
        "Hello ${#recipient}, the order ID is ${id}.",
        templateContext);

String message = template.getValue(context, String.class);
```

In this case, `${` starts an expression segment and `}` ends it. The two parameters are delimiter strings chosen by the application; the same `ParserContext` must be used consistently when parsing the template.

`TemplateParserContext` implements `ParserContext` and provides three key pieces of information: this is a template (`isTemplate()` returns `true`), the expression prefix, and the expression suffix. If more specialized parsing rules are needed, the application can implement `ParserContext` itself; in most cases, `TemplateParserContext` is sufficient.

When literal text contains the chosen delimiter string itself, switch to a different delimiter pair that does not appear in the content. Choosing clear delimiters helps the parser distinguish text parts from expression parts.

## 6. Templates are parsed and evaluated at two separate times

There are two separate steps:

1. **Parse:** `parseExpression(templateText, templateContext)` splits literal text from SpEL segments and checks the syntax of the expression segments.
2. **Evaluate:** `getValue(evaluationContext, String.class)` executes the SpEL segments using data in the context and concatenates the results with the literal text.

You can parse a template once and evaluate it multiple times with different contexts, as long as the required root objects, variables, and access capabilities are provided for each evaluation.

Example:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression template = parser.parseExpression(
        "Hello #{#name}!",
        new TemplateParserContext());

StandardEvaluationContext firstContext = new StandardEvaluationContext();
firstContext.setVariable("name", "An");
String first = template.getValue(firstContext, String.class);

StandardEvaluationContext secondContext = new StandardEvaluationContext();
secondContext.setVariable("name", "Binh");
String second = template.getValue(secondContext, String.class);
```

`first` is `Hello An!`; `second` is `Hello Binh!`. The parsed template is reused, while the dynamic values come from the context on each evaluation.

## 7. TemplateParserContext vs. SpelParserConfiguration

These two components solve two different problems:

| Component | Responsibility |
| --- | --- |
| `TemplateParserContext` | Indicates that the input is a template and defines the prefix/suffix to separate literal text from SpEL segments. |
| `SpelParserConfiguration` | Configures parser/engine behavior, such as auto-growing collections or auto-growing null references and compiler mode. |

For example, if you need to configure the parser and parse a template at the same time, you can pass the configuration to `SpelExpressionParser` and then pass `TemplateParserContext` to `parseExpression`:

```java
SpelParserConfiguration configuration = new SpelParserConfiguration();
ExpressionParser parser = new SpelExpressionParser(configuration);
ParserContext templateContext = new TemplateParserContext();

Expression template = parser.parseExpression(
        "Product: #{name}",
        templateContext);
```

Do not use `SpelParserConfiguration` to change template delimiters; that is the responsibility of `ParserContext`.

## 8. Common errors and how to handle them

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Plain text sentence reports a SpEL syntax error | Called the `parseExpression` overload without `ParserContext`, so the entire string was treated as an expression. | Pass `new TemplateParserContext()` or a custom context. |
| Expression segment is not recognized | The prefix in the content does not match the context's prefix. | Verify the exact configured prefix/suffix pair. |
| Missing suffix or parse error at end of template | There is an opening prefix without a corresponding suffix. | Add the closing delimiter and inspect the assembled template string. |
| Property or variable error when calling `getValue` | Template syntax is valid, but the required root object, variable, or resolver is missing from the evaluation context. | Check the context at evaluation time, such as the root object and `setVariable`. |
| Result has an improperly formatted value | Expression value is converted to string using existing conversion mechanisms; display formatting may not fit. | Format data at the application layer or use controlled expressions/helpers to produce the desired string. |
| Literal text is misinterpreted as an expression | Content contains the active delimiter itself. | Choose a custom delimiter pair that does not conflict with the text. |

## 9. Notes when using templates in applications

- Only put SpEL expressions controlled by the application into templates. `TemplateParserContext` is not a sanitization or sandboxing mechanism for untrusted expressions.
- If users only supply data, pass the data via variables in `EvaluationContext` instead of concatenating that data into the expression string.
- Restrict property accessors, method resolvers, type locators, and bean resolvers according to actual needs if templates can come from external sources.
- Check for both parse errors and evaluation errors: parsing may succeed while evaluation still fails if a property, variable, or bean does not exist.
- Choose delimiters unlikely to appear in literal text and keep configuration consistent across templates.

## Key takeaways

- Use `parseExpression(text)` for a standalone SpEL expression.
- Use `parseExpression(text, new TemplateParserContext())` when the string consists of literal text and `#{...}` segments.
- `TemplateParserContext()` defaults to prefix `#{` and suffix `}`; the two-parameter constructor allows customizing delimiters.
- Segments inside delimiters still follow SpEL's normal syntax and evaluation rules.
- `parseExpression` creates the expression; `getValue` is what evaluates the dynamic segments using `EvaluationContext` and builds the resulting string.
- `TemplateParserContext` controls how templates are split; `SpelParserConfiguration` controls other parser configuration behaviors.