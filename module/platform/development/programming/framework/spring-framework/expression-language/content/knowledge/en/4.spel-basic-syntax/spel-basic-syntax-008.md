# Distinguishing Raw Text from Parts Evaluated by SpEL

## 1. Why Distinguish These Two Kinds of Content?

Spring Expression Language (SpEL) lets applications describe values, conditions, and object operations using an expression string. However, not every string containing SpEL-like symbols is automatically evaluated by Spring.

We must distinguish:

- **Raw text:** content kept as a character string. For example, `"Hello customer"` is just text if it has not been passed through an expression processing mechanism.
- **SpEL expression:** content interpreted by the parser according to SpEL grammar and evaluated within an `EvaluationContext`.
- **Template:** a string containing both raw text and one or more SpEL segments marked by delimiters. Text outside delimiters is preserved as-is; parts inside delimiters are parsed and evaluated.

This distinction directly affects the return value, parser configuration, how Spring processes annotations, and security when content comes from users.

## 2. Normal Parsing Treats the Entire String as an Expression

When calling `ExpressionParser.parseExpression(String)` without passing a `ParserContext`, the parser defaults to treating the entire input string as a SpEL expression.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression("2 + 3 * 4");
    Integer result = expression.getValue(Integer.class);

    // result = 14

The entire string `2 + 3 * 4` is SpEL syntax. The parser does not treat any part of it as a message or display text for the user.

If you pass an ordinary sentence:

    Expression expression =
        parser.parseExpression("Hello customer");

then the parser will try to interpret those words as identifiers or syntactic constructs. This string does not automatically become a text message. Normally it will raise a parse error because it is not valid expression syntax.

If you want the expression to return a literal string, write the string using SpEL literal syntax:

    Expression expression = parser.parseExpression("'Hello customer'");
    String message = expression.getValue(String.class);

In this case, the single quotes are part of SpEL syntax; the returned value is the string excluding the quotes.

Rule to remember: with normal parsing, the entire input is SpEL. To keep a text value, use a SpEL string literal or do not pass that content through the parser.

## 3. Templates Combine Raw Text and Expressions

When you need to construct a string with both fixed text and dynamic values, use template parsing.

Spring provides `TemplateParserContext`, an implementation of `ParserContext`. By default, it uses:

- Prefix: `#{`
- Suffix: `}`

Only content between the delimiter pair is parsed as a SpEL expression. The rest is raw text.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Hello, #{'Spring'}!",
        new TemplateParserContext()
    );

    String message = template.getValue(String.class);

    // message = "Hello, Spring!"

In the input string:

| Segment | How It Is Handled |
| --- | --- |
| `Hello, ` | Raw text, preserved as-is |
| `#{'Spring'}` | SpEL expression, evaluated to `Spring` |
| `!` | Raw text, preserved as-is |

The final result is a string assembled from the text segments and expression results.

You can place multiple expressions in the same template:

    String source =
        "Order #{#order.id} has total #{#order.total}.";

    Expression template = parser.parseExpression(
        source,
        new TemplateParserContext()
    );

    String message = template.getValue(context, String.class);

Each segment inside delimiters is evaluated in the provided context. Text parts outside are not interpreted as SpEL.

## 4. Supplying Data for the Expression Part

A template only defines which part needs to be evaluated. Dynamic values still need to be provided via the root object or `EvaluationContext`.

Example using variables:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Hello #{#customerName}, order ID is #{#orderId}.",
        new TemplateParserContext()
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customerName", "Lan");
    context.setVariable("orderId", "ORD-2026-001");

    String message = template.getValue(context, String.class);

Result:

    Hello Lan, order ID is ORD-2026-001.

Pay attention to the variable syntax with the `#` symbol. In a template, `#{...}` is the delimiter surrounding the expression; whereas `#customerName` is how the expression references the variable named `customerName`.

These two symbols have different roles:

- `#{...}` defines the expression boundary in the template.
- `#name` references the variable named `name` inside the expression.

You can use a root object instead of variables:

    Expression template = parser.parseExpression(
        "Customer #{name} has score #{score}.",
        new TemplateParserContext()
    );

    String message = template.getValue(customer, String.class);

In this example, `name` and `score` are looked up on the root object using the default evaluation context's property access mechanism. The exact access behavior depends on the object and configured accessors.

## 5. Configuring Delimiters with ParserContext

`ParserContext` describes how the parser recognizes a template. In addition to the default `TemplateParserContext`, an application can define custom delimiters by implementing this interface.

Example using custom prefix and suffix:

    ParserContext parserContext = new ParserContext() {
        @Override
        public boolean isTemplate() {
            return true;
        }

        @Override
        public String getExpressionPrefix() {
            return "${";
        }

        @Override
        public String getExpressionSuffix() {
            return "}";
        }
    };

    Expression template = parser.parseExpression(
        "Hello ${#customerName}!",
        parserContext
    );

In this example, `${...` is not the default syntax of `TemplateParserContext`; it only works because the application supplied a `ParserContext` using that delimiter.

Do not change delimiters in code without coordinating with where the template is created. The parser and the template source must follow the same convention so text parts are not misinterpreted or expressions fail to be recognized.

## 6. Distinguishing SpEL Delimiters from Property Placeholders

In Spring applications, two common forms of notation are:

- `${property.name}`: placeholder to retrieve a configuration value from `Environment` or a registered property source.
- `#{expression}`: SpEL expression evaluated by Spring at integration points that support expressions.

Example:

    @Value("${app.display-name}")
    private String displayName;

Spring replaces the placeholder with the value of the `app.display-name` property if placeholder configuration has been set up for the application environment.

Example using SpEL:

    @Value("#{systemProperties['user.name']}")
    private String operatingSystemUser;

Here, the content inside `#{...}` is a SpEL expression. Spring evaluates the expression in the bean factory's context and converts the result to the target field or parameter type if needed.

You can combine text with expressions in a value processed by Spring:

    @Value("Application: ${app.display-name}, user: #{systemProperties['user.name']}")
    private String startupMessage;

In this example:

- `${app.display-name}` is a configuration placeholder.
- `#{systemProperties['user.name']}` is the SpEL part.
- `Application: ` and `, user: ` are fixed text.

This is the behavior of Spring's value-processing mechanism, not a rule that Java strings perform on their own. If you merely assign that string to an ordinary Java variable, Java preserves the `${...}` and `#{...}` characters as-is; no placeholder resolver or SpEL parser runs automatically.

Do not equate `${...}` with `#{...}`: placeholder resolution and SpEL evaluation are two separate mechanisms, even though they can appear together in a configuration value processed by Spring.

## 7. Different Contexts Have Different Processing Rules

The same string can yield different results depending on where it is used.

| Context | Behavior |
| --- | --- |
| Ordinary Java string | Preserves characters as-is; does not automatically evaluate SpEL |
| `parseExpression(source)` | Treats the entire source as one expression |
| `parseExpression(source, new TemplateParserContext())` | Keeps text outside delimiters and evaluates the part inside `#{...}` |
| `@Value` in Spring | Spring resolves placeholders and expressions according to the container's integration mechanism |
| String passed to a custom business API | Only evaluated if that API actively calls a parser or resolver |

For example, the same content:

    "Hi #{#name}"

can have three outcomes:

1. In an ordinary Java string, the result remains literally `Hi #{#name}`.
2. When parsed as a standalone expression, the parser tries to interpret the entire string as SpEL and normally reports a syntax error.
3. When parsed with a template context and supplied the `name` variable, the result is `Hi Lan` if the variable has the value `Lan`.

Therefore, when debugging an unreplaced string, first identify which component is processing it: Java, Spring's placeholder resolver, the SpEL parser, or a custom API.

## 8. Return Values and Data Types

When using a template, the final result is a concatenated string. Expressions inside can still return various data types; that value is converted into the corresponding content part in the template result.

Example:

    Expression template = parser.parseExpression(
        "Quantity: #{#quantity}, in stock: #{#available}",
        new TemplateParserContext()
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("quantity", 3);
    context.setVariable("available", true);

    String message = template.getValue(context, String.class);

Result:

    Quantity: 3, in stock: true

If you want to obtain a value of a specific type directly, use a standalone expression and request the result type:

    Expression expression = parser.parseExpression("#quantity * 2");

    Integer doubled = expression.getValue(context, Integer.class);

Templates are suited for display content or composite strings. Standalone expressions are suited for calculations or typed values used further in application logic.

If cast to an incompatible result type, evaluation or type conversion may fail. Do not rely on every result automatically converting to the type the application expects.

## 9. Common Mistakes When Mixing Raw Text and SpEL

### Using Plain Text in Normal Parsing

Wrong:

    parser.parseExpression("Hello #{#name}");

Without passing a template context, the parser treats the whole string as SpEL. Plain text can cause parsing to fail.

Proper way when mixing text and expressions:

    parser.parseExpression(
        "Hello #{#name}",
        new TemplateParserContext()
    );

### Forgetting Template Delimiters

When using `TemplateParserContext`, the dynamic part must be placed inside the configured delimiters. A variable outside delimiters is just text.

Example:

    "Hello #name"

is not equivalent to:

    "Hello #{#name}"

In the second example, only the `#name` part is recognized by the parser as an expression.

### Confusing Variable Markers with Template Markers

`#name` is a variable reference in SpEL. `#{...}` is the default delimiter to mark an expression in a template. Missing a symbol or placing it in the wrong position can completely change how the parser interprets the string.

### Thinking Java Evaluates Strings Automatically

Assigning a string containing `#{...}` to a field or passing it to a Java method does not make SpEL run. There must be a component actively calling the parser or a Spring integration point that supports expressions.

### Confusing Placeholders and SpEL

`${app.name}` is used for property lookup. `#{...}` is used for SpEL. If you want to compute, access beans, or read objects via expressions, use SpEL at an integration point that supports it. If you only want to retrieve a configuration value, a placeholder is usually clearer and more appropriate.

## 10. Protecting the Boundary Between Text and Expressions

A template can execute logic. Therefore, if a user supplies content containing the `#{...}` delimiter and the application parses that entire content as a template, the user may accidentally or intentionally inject expressions into the evaluation flow.

Some security principles:

- Do not parse arbitrary user-entered content as a SpEL template.
- Distinguish application-controlled templates from user-supplied text data.
- Only allow necessary expressions inside controlled templates.
- Provide an evaluation context with the minimal set of variables, objects, accessors, and resolvers.
- For limited data-binding needs, consider `SimpleEvaluationContext` instead of a full-permission context.
- If you need to display delimiter-like symbols literally, process or escape the content according to clear application rules before passing it to the parser.

Changing delimiters does not automatically create a security boundary. If users can submit content containing the new delimiter and the application still parses it, expressions can still be evaluated.

## 11. Choosing the Right Processing Approach

You can decide based on your goal:

| Need | Suitable Approach |
| --- | --- |
| Keep a sentence unchanged | Use a Java string or normal text data |
| Return a literal string from SpEL | Use a string literal in the expression, e.g., `'Hello'` |
| Compute or retrieve a typed value | Use normal `parseExpression` |
| Combine text with dynamic values | Use template parsing with `TemplateParserContext` |
| Read a configuration property | Use a `${...}` placeholder at a Spring-supported point |
| Produce a dynamic value in `@Value` | Use a `#{...}` expression |
| Display user-entered content | Keep content as data; do not automatically parse as SpEL |

Before writing or debugging a string, ask yourself: is the entire string an expression, are only a few segments expressions, or is all of it just text? The answer determines whether to use the normal parser, the template parser, or no SpEL at all.

## 12. Key Points to Remember

- Java strings do not automatically run SpEL.
- `parseExpression(String)` treats the entire input as an expression.
- `TemplateParserContext` defaults to `#{` and `}` to separate expression parts from text.
- Text outside delimiters is preserved; content inside is parsed and evaluated.
- `#name` is a variable reference, distinct from the `#{...}` delimiter.
- `${...}` is a property placeholder; `#{...}` is SpEL in Spring integration points.
- Template parsing returns a composite string; normal expressions can return typed values.
- Parsing an untrusted template can allow user-injected expressions to be evaluated; control both the template source and the evaluation context.

Clearly distinguishing raw text, expressions, and templates helps avoid parse errors, prevents confusion between placeholders and SpEL, and preserves control over what content is allowed to execute in the application.
