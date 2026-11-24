# Initializing a SpEL Parser and Creating an Expression

## 1. Role of the parser and expression

Spring Expression Language (SpEL) provides an expression language for reading properties, accessing collections, comparing, computing, and invoking methods on objects at runtime. When using SpEL directly in Java, the two most important abstractions are:

- `ExpressionParser`: takes an expression string and parses its syntax.
- `Expression`: represents the parsed expression; you use it to retrieve values or update values against an evaluation context/root object.

`SpelExpressionParser` is the common implementation of `ExpressionParser`. The basic usage flow consists of three steps: creating a parser, calling `parseExpression(...)` to obtain an `Expression`, and calling `getValue(...)` with the data to evaluate.

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'Hello, SpEL!'");
String message = expression.getValue(String.class);

System.out.println(message); // Hello, SpEL!
~~~

The string `'Hello, SpEL!'` is a valid SpEL expression: it returns a string literal. The single quotes belong to SpEL syntax. The `#{...}` delimiters commonly seen in Spring annotations such as `@Value` are not needed when calling `parseExpression` directly with a regular expression.

## 2. Required dependencies

If the application does not use another Spring module that pulls in SpEL transitively, you can declare the `spring-expression` module directly:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-expression</artifactId>
</dependency>
~~~

If the project uses Spring Boot dependency management or the Spring Framework BOM, let the BOM manage the module version to keep Spring modules on the same version. In a typical Spring application, `spring-expression` is usually already on the classpath through related dependencies.

Key imports in the parser examples:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
~~~

## 3. Creating the parser

The default way to initialize it is by calling the no-argument constructor:

~~~java
ExpressionParser parser = new SpelExpressionParser();
~~~

The default parser handles standard SpEL syntax. You can keep the parser in a shared application component if it fits the lifecycle and code organization. Parsing and evaluation are two distinct operations: `parseExpression` creates an `Expression`, whereas `getValue` evaluates the expression against specific data/context.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression taxExpression = parser.parseExpression("price * 0.1");
Expression labelExpression = parser.parseExpression("'Order-' + #orderId");
~~~

An expression can be evaluated against different root objects or evaluation contexts, as long as the provided data matches the properties and variables referenced by the expression.

## 4. Creating an Expression from a string

The most commonly used method is:

~~~java
Expression expression = parser.parseExpression("2 + 3 * 4");
~~~

`parseExpression(String)` accepts a string containing a complete SpEL expression and returns an `Expression` object. Some examples:

| Input string | Meaning |
|---|---|
| `"42"` | Integer literal |
| `"'Spring'"` | String literal |
| `"true"` | Boolean literal |
| `"2 + 3 * 4"` | Arithmetic operation |
| `"'spring'.toUpperCase()"` | Method call on a string |
| `"items[0]"` | Accessing the first element |
| `"customer.address.city"` | Accessing a nested property |
| `"total >= 1000 and active"` | Combining logical conditions |

After parsing, retrieve the result with `getValue`:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("2 + 3 * 4");

Object rawValue = expression.getValue();
Integer result = expression.getValue(Integer.class);

System.out.println(rawValue); // 14
System.out.println(result);   // 14
~~~

`getValue()` returns an `Object`; the overload taking `Class<T>` requests the result in the desired type and uses SpEL's type conversion mechanism if needed. You should specify the target type when the application already knows the expected data type, so that the code clearly expresses the output contract.

## 5. Evaluating an expression against a root object

When an expression references properties such as `name` or `address.city`, the parser needs to know the root object to resolve those names. You can pass the root object directly into `getValue`.

Example of a JavaBean:

~~~java
public class Person {
    private String name;

    public Person(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Create an expression and evaluate it against the object:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

Person person = new Person("Lan");
String name = expression.getValue(person, String.class);

System.out.println(name); // Lan
~~~

Here `person` is the root object. SpEL resolves `name` through the property accessors of the evaluation mechanism. You can traverse deeper into the object graph if the intermediate properties exist:

~~~java
Expression cityExpression =
        parser.parseExpression("address.city");

String city = cityExpression.getValue(person, String.class);
~~~

The second example evaluates successfully only if the passed-in object has an `address` property and that object has a `city` property. If a property does not exist or an intermediate value is null, evaluation may raise an error depending on the expression and parser configuration.

## 6. Using EvaluationContext for the root object and variables

When you need to declare variables or customize how an expression accesses data, use `EvaluationContext`. `StandardEvaluationContext` provides fuller evaluation capabilities, including the root object, variables, property accessors, method resolvers, type locator, and bean resolver when configured.

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

ExpressionParser parser = new SpelExpressionParser();

Person person = new Person("Lan");
StandardEvaluationContext context =
        new StandardEvaluationContext(person);

context.setVariable("prefix", "Hello");

Expression expression =
        parser.parseExpression("#prefix + ' ' + name");

String greeting = expression.getValue(context, String.class);

System.out.println(greeting); // Hello Lan
~~~

Some rules to remember:

- Variable names in the context are referenced with the `#` prefix, for example `#prefix`.
- The root object is accessed directly by property name, for example `name`.
- `#root` represents the current root object.
- `#this` represents the object currently being processed at the current position in a collection projection or selection.

Multiple variables can be set:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("quantity", 3);
context.setVariable("unitPrice", 12.5);

Expression expression =
        parser.parseExpression("#quantity * #unitPrice");

Double subtotal = expression.getValue(context, Double.class);
~~~

Separating input data into variables keeps the expression from embedding actual data directly in the string. This approach also makes it possible to reuse the same expression with many different sets of values.

## 7. Distinguishing between parsing an expression and evaluating an expression

These two operations have different responsibilities:

~~~java
Expression expression = parser.parseExpression("total * 1.1");
BigDecimal amount = expression.getValue(order, BigDecimal.class);
~~~

- `parseExpression` validates and parses the string syntax. It produces an `Expression` representation for later use.
- `getValue` evaluates the expression against a specific root object or evaluation context. Errors due to nonexistent properties, null data, uncallable methods, or failed type conversions typically occur at this step.

Therefore, a syntactically valid string may still fail to evaluate against a specific object. For example, `customer.name` may parse successfully yet fail when the root object has no `customer` property, or when that property cannot provide a suitable value.

If the application evaluates the same expression multiple times, you can parse it upfront and keep the `Expression` for reuse instead of re-parsing the string on every call:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression discountExpression =
        parser.parseExpression("total > 1000 ? total * 0.9 : total");

// For each evaluation, pass the corresponding order object.
BigDecimal firstDiscount =
        discountExpression.getValue(firstOrder, BigDecimal.class);
BigDecimal secondDiscount =
        discountExpression.getValue(secondOrder, BigDecimal.class);
~~~

This approach separates the expression structure from runtime data and makes the processing flow easier to read.

## 8. Using ParserContext when the string is a template

By default, `parseExpression(String)` interprets the entire string as an expression. If the string contains fixed text interspersed with SpEL segments, pass an additional `ParserContext`, typically `TemplateParserContext`:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ParserContext;
import org.springframework.expression.common.TemplateParserContext;

ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
        "Hello #{#person.name}, your score is #{#score}",
        templateContext);
~~~

During evaluation, segments inside `#{...}` are processed as SpEL; text outside is kept as-is and combined into the result:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("person", new Person("Lan"));
context.setVariable("score", 95);

String message = expression.getValue(context, String.class);
// Hello Lan, your score is 95
~~~

You can choose a different prefix and suffix using the `TemplateParserContext` constructor:

~~~java
ParserContext customTemplate =
        new TemplateParserContext("${", "}");

Expression expression = parser.parseExpression(
        "Hello ${#person.name}",
        customTemplate);
~~~

Use a template context only when the input is genuinely a template. If you pass a string containing regular text into the default parser, the parser will attempt to parse the entire string as an expression and may report a syntax error.

## 9. Configuring the parser when auto-growing objects/collections is needed

In some situations, SpEL needs to automatically initialize null properties or grow collections when accessing an index beyond the current size. You can configure this behavior with `SpelParserConfiguration`:

~~~java
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpressionParser;

SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

The two flags in this constructor enable auto-grow for null references and collections, respectively. When enabled, evaluating an expression can modify the object graph or collection size to satisfy the access path. Enable this only when that behavior suits the data model and application constraints; do not treat it as an object initialization mechanism replacing clear domain design.

## 10. Updating values through Expression

Besides reading values, `Expression` can also write to writable properties:

~~~java
Person person = new Person("Lan");

Expression nameExpression = parser.parseExpression("name");
nameExpression.setValue(person, "Minh");

System.out.println(person.getName()); // Minh
~~~

Or pass an evaluation context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(person);

Expression nameExpression = parser.parseExpression("name");
nameExpression.setValue(context, "Minh");
~~~

A write operation succeeds only when the target property can be updated through an appropriate property accessor. For immutable objects, read-only properties, or unmodifiable collections, the call may raise an error. Use `setValue` intentionally because it mutates object state at runtime.

## 11. Handling parse errors and evaluation errors

There are two common groups of errors:

- **Parse error**: the string does not follow valid SpEL syntax, such as missing parentheses, operators, or quotes.
- **Evaluation error**: the syntax is valid, but cannot be evaluated against the current data/context, such as a nonexistent property, traversing through null, calling an incompatible method, or failed type conversion.

The API uses exceptions in the `org.springframework.expression` package, where `ParseException` represents a parse error and `EvaluationException` represents an evaluation error. Specific SpEL exceptions can provide character positions and more detailed information.

~~~java
import org.springframework.expression.EvaluationException;
import org.springframework.expression.ParseException;

try {
    Expression expression = parser.parseExpression("customer..name");
    String name = expression.getValue(order, String.class);
} catch (ParseException ex) {
    // Record that the expression has invalid syntax.
} catch (EvaluationException ex) {
    // Record the error when evaluating against the data/context.
}
~~~

In production code, log enough information to identify the expression and error context while avoiding logging sensitive object data. If expressions come from configuration, validate the configuration early at application startup to catch errors before real requests flow through the processing pipeline.

## 12. Notes on access permissions and untrusted expressions

`StandardEvaluationContext` can allow property access, method invocation, type references, or bean references depending on the configured resolvers/accessors. Therefore, you should not take arbitrary SpEL strings from users and evaluate them with a context that has full application privileges.

If you only need data binding with a limited set of properties, consider `SimpleEvaluationContext` and explicitly configure the allowed capabilities. Choosing an evaluation context should be based on the types of data and operations the expression is permitted to perform. Restricting the context is part of security design, not merely a syntax choice.

## 13. Common usage workflow

When integrating SpEL in a Java class, you can follow this sequence:

1. Create a `SpelExpressionParser` or a parser with the appropriate configuration.
2. Call `parseExpression` with a plain expression; pass a `ParserContext` if processing a template.
3. Prepare the root object or `EvaluationContext`, including any needed variables.
4. Call `getValue` with the desired result type.
5. Handle parse errors and evaluation errors separately at the appropriate boundary.
6. Reuse the `Expression` when the same expression structure is evaluated multiple times.

Combined example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "#quantity * #unitPrice");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("quantity", 4);
context.setVariable("unitPrice", 25);

BigDecimal total = expression.getValue(context, BigDecimal.class);
~~~

In this example, the parser is only responsible for parsing the string. The context supplies the input data, and the expression returns the evaluated result. When `quantity` or `unitPrice` changes, you can update the variables in the context and re-evaluate the same expression.

## 14. Key takeaways

- `SpelExpressionParser` is the implementation used to parse SpEL strings.
- `parseExpression` creates an `Expression`; `getValue` is what actually evaluates the expression against data.
- With a root object, properties can be referenced directly such as `name`; variables in the context use the `#` prefix.
- Use `StandardEvaluationContext` when full evaluation capabilities are needed and `SimpleEvaluationContext` when you want to restrict access capabilities.
- Use `ParserContext`/`TemplateParserContext` when a string contains fixed text interspersed with expressions.
- Auto-grow can be configured with `SpelParserConfiguration`, but you must understand its impact on objects/collections.
- Distinguish parse errors from evaluation errors to handle the root cause properly.
- Do not evaluate untrusted expressions with a context that has broad access privileges.
