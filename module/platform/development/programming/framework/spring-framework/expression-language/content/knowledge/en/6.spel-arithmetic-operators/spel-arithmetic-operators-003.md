# Distinguishing Raw Text from SpEL-Evaluated Content

## 1. Three Types of Content to Distinguish

Spring Expression Language (SpEL) allows an application to describe values, conditions, and operations on objects using an expression string. However, a character string is only evaluated when it passes through a parser or a Spring integration point that supports SpEL.

In practice, there are three types of content:

- **Raw text:** a string kept as-is as data. For example, `"Hello customer"` does not automatically become an expression.
- **SpEL expression:** the entire string is interpreted by the parser according to the SpEL grammar. For example, `2 + 3 * 4`.
- **Template:** a string consisting of raw text and one or more expression segments marked by delimiters. For example, `"Hello #{#customer.name}"`.

This distinction determines how the parser interprets the string, what type the returned result has, and which content is actually executed.

## 2. Java Strings Do Not Automatically Run SpEL

A Java string is only data:

    String message = "Hello #{#customer.name}";

    System.out.println(message);

The output is still:

    Hello #{#customer.name}

The Java compiler and JVM do not automatically look for `#{...}` markers to evaluate expressions. If the application wants to substitute the dynamic part, it must call a template-processing API, or pass the string through a Spring integration point that supports SpEL.

This is very important when debugging. If a message still contains literal `#{...}`, determine whether the string has been passed through the right processor or was only stored, read, or passed through Java methods.

## 3. Standard Parsing Treats the Entire Input as an Expression

When calling `ExpressionParser.parseExpression(String)` without passing a `ParserContext`, the parser treats the entire input string as a SpEL expression.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression("2 + 3 * 4");
    Integer result = expression.getValue(Integer.class);

    // result = 14

The entire string `2 + 3 * 4` is SpEL syntax. The parser does not split it into text and expression.

If an ordinary sentence is passed:

    Expression expression =
        parser.parseExpression("Hello customer");

the parser still tries to interpret those words as identifiers or syntax elements. This string does not automatically become a text message; normally it will cause a parse error because it is not a valid SpEL expression.

If you want an expression to return a literal string, use SpEL's literal syntax:

    Expression expression =
        parser.parseExpression("'Hello customer'");

    String message = expression.getValue(String.class);

The single quotes belong to the expression syntax. The returned value is the string `Hello customer`, without the quotes.

Use standard parsing when the entire input itself is logic or a SpEL value. If the input is a sentence with dynamic values inserted, use template parsing.

## 4. Templates Preserve Text Outside Delimiters

Spring provides `TemplateParserContext`, an implementation of `ParserContext`. By default configuration, templates use:

- Prefix: `#{`
- Suffix: `}`

Only content inside the two delimiters is parsed as SpEL. Segments outside are preserved as text.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Hello, #{'Spring'}!",
        new TemplateParserContext()
    );

    String message = template.getValue(String.class);

    // message = "Hello, Spring!"

The input string can be broken down into three parts:

| Segment | How It Is Processed |
| --- | --- |
| `Hello, ` | Raw text, kept as-is |
| `#{'Spring'}` | SpEL, evaluated to `Spring` |
| `!` | Raw text, kept as-is |

The final result is a string concatenated from the text segments and the values returned by the expressions.

Multiple expressions can be placed in a single template:

    String source =
        "Order #{#order.id} has total amount #{#order.total}.";

    Expression template = parser.parseExpression(
        source,
        new TemplateParserContext()
    );

    String message = template.getValue(context, String.class);

Each segment inside delimiters is evaluated in the provided context. The text outside is not interpreted as SpEL.

## 5. Expression Parts Retrieve Data from EvaluationContext

A template defines the boundary between text and expression. It does not automatically generate data for variables referenced inside the expression.

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

Distinguish two ways symbols are used:

- `#{...}` is the delimiter marking the expression boundary in a template.
- `#customerName` is a variable reference inside an expression.

A root object can be used instead of variables:

    Expression template = parser.parseExpression(
        "Customer #{name} has score #{score}.",
        new TemplateParserContext()
    );

    String message = template.getValue(customer, String.class);

In this example, `name` and `score` are accessed on the root object according to the evaluation context's property accessor. Actual access depends on the object and configured accessors.

## 6. Custom Delimiters Can Be Used

`ParserContext` describes how the parser recognizes a template. If an application needs different delimiters, `TemplateParserContext`'s constructor can be used to configure the prefix and suffix.

Example using `[[` and `]]`:

    ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

    Expression template = parser.parseExpression(
        "Hello [[#customerName]]!",
        parserContext
    );

The delimiters in this example only take effect because the parser is passed the corresponding `parserContext`. If the template source and the parser do not agree on delimiters, dynamic segments may be kept as text or the parser may process the string differently than expected.

Changing delimiters does not automatically change the inner SpEL grammar. It only changes how the template recognizes the boundary between text and expression.

## 7. Distinguishing SpEL from Property Placeholders

In Spring applications, two common notations are:

- `${property.name}`: a placeholder used to look up a configuration value from `Environment` or registered property sources.
- `#{expression}`: a SpEL expression evaluated at integration points that support expressions.

Placeholder example:

    @Value("${app.display-name}")
    private String displayName;

Spring replaces the placeholder with the value of the `app.display-name` property if placeholder resolution has been set up in the application environment.

SpEL example:

    @Value("#{systemProperties['user.name']}")
    private String operatingSystemUser;

The content inside `#{...}` is a SpEL expression. Spring evaluates it in the bean factory context and converts the result to the target field or parameter type if needed.

Both can be combined in a single value processed by Spring:

    @Value("Application: ${app.display-name}, user: #{systemProperties['user.name']}")
    private String startupMessage;

In this example:

- `${app.display-name}` is processed as a property placeholder.
- `#{systemProperties['user.name']}` is processed as SpEL.
- `Application: ` and `, user: ` are fixed text.

This is the behavior of Spring's value resolution mechanism, not a Java string rule. If that string is assigned to an ordinary Java variable, the `${...}` and `#{...}` characters remain unchanged.

Do not equate placeholder resolution with SpEL evaluation. Both mechanisms can appear together in a configuration value, but they have different purposes and processing components.

## 8. Each Context Has Its Own Processing Rules

The same string can yield different results depending on where it is used:

| Context | Behavior |
| --- | --- |
| Ordinary Java string | Keeps characters intact; does not auto-evaluate |
| `parseExpression(source)` | Treats the entire source as an expression |
| `parseExpression(source, new TemplateParserContext())` | Keeps text outside delimiters and evaluates what is inside `#{...}` |
| `@Value` in Spring | Spring processes placeholders and expressions via container integration |
| Custom business API | Only evaluates if the API explicitly invokes a parser or resolver |

For example, the string:

    "Hello #{#name}"

can be handled in three ways:

1. In an ordinary Java string, it stays verbatim `Hello #{#name}`.
2. When parsed as a standalone expression, the parser tries to interpret the entire string as SpEL and usually reports a syntax error.
3. When parsed with a template context and given the `name` variable, the result is `Hello Lan` if the variable has the value `Lan`.

When debugging an unsubstituted string, identify which component is processing it: Java, Spring placeholder resolver, SpEL parser, or a custom API.

## 9. Result Types of Expressions and Templates

A standalone expression can return a value of a specific type:

    Expression expression = parser.parseExpression("#quantity * 2");

    Integer doubled =
        expression.getValue(context, Integer.class);

Templates are used to build composite strings. Expressions inside can return numbers, booleans, or objects; the results are converted into corresponding content in the final string.

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

Use templates for display content or composite strings. Use standalone expressions when the application needs a typed value for further logic processing.

If the requested result type is incompatible with the actual value, evaluation or type conversion may fail. Do not assume every expression can be converted to the desired type.

## 10. Common Mistakes When Mixing Raw Text and SpEL

### Passing Plain Text to the Standard Parser

Example:

    parser.parseExpression("Hello #{#name}");

Without passing a template context, the parser treats the whole string as SpEL. The text part may cause parsing to fail.

To mix text and expressions, use:

    parser.parseExpression(
        "Hello #{#name}",
        new TemplateParserContext()
    );

### Placing a Variable Outside Delimiters

The string:

    "Hello #name"

is not equivalent to:

    "Hello #{#name}"

In a template, only the part inside delimiters is evaluated. `#name` standing outside delimiters is just text characters.

### Confusing Variable Markers with Template Markers

`#name` is how variables are referenced in SpEL. `#{...}` is the default delimiter marking expressions in a template. Missing a character or misplacing one can change how the parser interprets the string.

### Assuming Java Automatically Evaluates

Assigning a string containing `#{...}` to a field or passing it through Java methods does not execute SpEL. A component must explicitly call a parser or a Spring integration point that supports expressions.

### Confusing Placeholders and SpEL

`${app.name}` looks up a configuration property. `#{...}` evaluates a SpEL expression. If you only need to retrieve a configuration value, a placeholder is usually clearer. If you need calculations or expression-based object access, use SpEL at an appropriate integration point.

## 11. Keeping a Boundary Between Data and Logic

Templates can execute logic. If users supply content containing `#{...}` delimiters and the application parses all of that content as a template, user-injected expressions can be evaluated.

Some guidelines:

- Do not automatically parse user-entered content as a SpEL template.
- Separate application-controlled templates from text data coming from users.
- Put only necessary variables and objects into the context.
- Restrict property accessors, method resolvers, and access capabilities according to business needs.
- Use `SimpleEvaluationContext` when only a limited data-binding feature set is needed.
- If literal delimiter-like characters need to be displayed, define escaping or content-handling rules before passing to the parser.

Changing delimiters does not by itself create a security boundary. If untrusted data is still passed into a parser with the new delimiters, expressions can still be evaluated.

## 12. Choosing the Right Approach

| Need | Approach |
| --- | --- |
| Keep a sentence verbatim | Use a Java string or text data |
| Return a literal string from SpEL | Use a string literal, e.g. `'Hello'` |
| Calculate or obtain a typed value | Use standard `parseExpression` |
| Combine text with dynamic values | Use template parsing with `TemplateParserContext` |
| Read a configuration property | Use `${...}` where Spring supports placeholders |
| Produce a dynamic value in `@Value` | Use a `#{...}` expression |
| Display user-entered content | Keep content as data; do not auto-parse as SpEL |

Before processing a string, determine whether the entire string is an expression or only a few segments are expressions. The answer determines whether to use the standard parser, template parser, or no SpEL at all.

## 13. Key Points to Remember

- Java strings do not automatically run SpEL.
- `parseExpression(String)` treats the entire input as an expression.
- `TemplateParserContext` defaults to `#{` and `}` to separate expressions from raw text.
- Text outside delimiters is preserved; content inside is parsed and evaluated.
- `#name` is a variable reference, distinct from the `#{...}` delimiter.
- `${...}` is a property placeholder; `#{...}` is SpEL at supported Spring integration points.
- Templates produce composite strings; standalone expressions can return typed values.
- Do not parse untrusted templates without controlling privileges in the evaluation context.

Distinguishing raw text, expressions, and templates helps prevent parsing errors, confusion between placeholders and SpEL, and clearly controls what content is allowed to execute in the application.
