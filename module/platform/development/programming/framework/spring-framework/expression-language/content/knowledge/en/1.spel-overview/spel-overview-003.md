# Placing Spring Expression Language Alongside Java Code, Configuration Placeholders, and Template Expressions

## 1. Four Ways of Expressing Values, Four Roles

In Spring, the same value can be produced or injected into an application using Java code, a property placeholder, Spring Expression Language (SpEL), or a template expression. They can appear side by side, but they are not the same kind of mechanism:

- **Java code** executes compiled logic. We invoke methods, access objects, and perform calculations using Java syntax.
- **Property placeholder** `${...}` looks up a configuration value by key from the Environment or property sources. It primarily replaces the key with its value.
- **SpEL** is an expression language parsed and evaluated by Spring at runtime. It can read properties, invoke methods, access collections, and compute over objects within an evaluation context.
- **Template expression** combines literal text with one or more evaluated expressions. With SpEL, the parser uses a template context to recognize the parts enclosed between delimiters, which default to `#{` and `}`.

The easiest pair to confuse is `${...}` and `#{...}`: the first usually means “retrieve a configuration value by name”; the second means “evaluate a SpEL expression”. Both can be used in Spring configuration, but they solve two different problems.

## 2. Java Code: Explicit and Compiled Logic

Suppose an application has a retry count configuration and needs to double that value, while ensuring the minimum result is 1:

```java
int configuredRetries = properties.getRetryCount();
int effectiveRetries = Math.max(configuredRetries * 2, 1);
```

This is plain Java. The compiler checks syntax and data types; the IDE can support renaming, navigation, and refactoring; the logic can be called from any suitable Java location. Readers clearly see where the data comes from and how the calculation is performed.

Java code is usually the right choice when the logic is part of business behavior, requires multiple branches, needs direct testing, or requires strict type checking. Putting a long calculation or complex business rule into a SpEL string usually makes the code harder to find, harder to refactor, and harder to debug.

## 3. Property Placeholder: Substituting Configuration Values

An `application.properties` file may contain:

```properties
app.name=Order Service
app.retry-count=3
app.timeout-ms=2500
```

Spring can inject these values into a bean using placeholders:

```java
@Component
class RetrySettings {
    private final int retryCount;
    private final long timeoutMs;

    RetrySettings(
            @Value("${app.retry-count}") int retryCount,
            @Value("${app.timeout-ms}") long timeoutMs) {
        this.retryCount = retryCount;
        this.timeoutMs = timeoutMs;
    }
}
```

`@Value("${app.retry-count}")` instructs Spring to look up the `app.retry-count` key in the property sources and convert the value to the target type if possible. Placeholders can declare a default value:

```java
@Value("${app.retry-count:3}")
private int retryCount;
```

If the key has no value, the part after the colon is used as the default. A placeholder is not an expression language: `${app.retry-count}` by itself does not invoke methods, does not access `order.customer.name`, and does not compute `retry-count * 2`. It only resolves a configuration key and returns the substituted value.

Use placeholders when the task is bringing external configuration into the application: URLs, queue names, timeouts, feature flags, retry counts, or environment information. If you need logic based on multiple objects or calculations, use Java or SpEL depending on the location and complexity.

## 4. SpEL: Evaluating Expressions on Objects at Runtime

SpEL allows expressing operations on objects using expression strings. For example, with an order object having `customer.name` and `total`:

```text
order.customer.name
order.total > 1000000
order.items[0].sku
```

Expressions can access nested properties, array/list/map indexes, comparisons, logical operators, arithmetic operators, and invoke methods permitted in the evaluation context. Some common syntaxes:

| Syntax | Meaning |
|---|---|
| `customer.name` | Reads property `name` from object `customer` |
| `#limit` | Reads variable named `limit` in the evaluation context |
| `#root` | The root object currently being evaluated |
| `items[0]` | Accesses an element by index |
| `total >= 1000` | Compares values |
| `T(java.lang.Math).max(2, 5)` | References a type and invokes a static method |
| `@pricingService.taxRate` | References a bean by name in a context with a bean resolver |

When using the parser directly in Java, the passed string is usually a plain expression without wrapping it in `#{...}`:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("total * 1.1");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

BigDecimal amount = expression.getValue(context, BigDecimal.class);
```

In this example, `order` is the root object. Therefore `total` is interpreted as a property of the root object. If you want to access named variables, use the `#` prefix and register the variables in the context:

```java
Expression expression = parser.parseExpression("#quantity * #unitPrice");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("quantity", 3);
context.setVariable("unitPrice", 12.5);

Double subtotal = expression.getValue(context, Double.class);
```

`ExpressionParser` parses the string into an `Expression`; `EvaluationContext` supplies the root object, variables, property accessors, method resolvers, and other capabilities to evaluate the expression. The same expression can produce different results when the context or input data differs.

In Spring configuration, SpEL commonly appears with `#{...}`, for example:

```java
@Value("#{T(java.lang.Math).max(3, 5)}")
private int retryFloor;
```

Here Spring recognizes the part inside `#{...}` as a SpEL expression and evaluates it to obtain the value assigned to the field. The `#{...}` syntax marks expressions in Spring configuration integration points; when calling `parseExpression("...")` directly, we usually pass the inner expression.

## 5. Side by Side in the Same Example

Suppose `app.retry-count=3`. There are three ways to obtain or transform the value:

**Retrieving configuration only with a placeholder:**

```java
@Value("${app.retry-count:3}")
private int retryCount;
```

The result is the configured retry count, or 3 by default. No calculation is performed by the placeholder.

**Computing with SpEL:**

```java
@Value("#{T(java.lang.Math).max(${app.retry-count:3} * 2, 1)}")
private int effectiveRetries;
```

Spring substitutes the placeholder with the configuration value, and then the SpEL expression performs the multiplication and calls `Math.max`. This example shows that the two mechanisms can work together: the placeholder supplies the configuration input, and SpEL evaluates the expression on that input. The configuration value must fit the expression; if a non-numeric string is put into `app.retry-count`, the multiplication cannot be evaluated.

**Computing with Java:**

```java
int effectiveRetries = Math.max(retrySettings.getRetryCount() * 2, 1);
```

The result can be equivalent, but the logic resides in Java and is type-checked by the compiler. When a rule begins to have multiple conditions, multiple steps, or needs testing as business behavior, Java is usually easier to maintain.

## 6. Template Expressions: Mixing Text with SpEL

A regular SpEL expression returns the result of the entire expression. A template expression is useful when we need to build a string containing both literal text and dynamic values, such as a notification:

```text
Order #{#order.code} for #{#order.customer.name} has total #{#order.total}
```

For the parser to treat the outer text as fixed content and only evaluate the segments inside `#{...}`, use `TemplateParserContext`:

```java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
        "Order #{#order.code} for #{#order.customer.name} "
                + "has total #{#order.total}",
        templateContext);

StandardEvaluationContext evaluationContext =
        new StandardEvaluationContext();
evaluationContext.setVariable("order", order);

String message = expression.getValue(
        evaluationContext, String.class);
```

`TemplateParserContext` uses `#{` as the default prefix and `}` as the default suffix. The parser preserves the text outside the expression segments, evaluates each SpEL segment, and concatenates the results into a string. You can create a parser context with a different prefix/suffix if your application format requires it.

Distinguish the two ways of calling it:

- `parseExpression("order.total")`: the entire string is a SpEL expression.
- `parseExpression("Total: #{order.total}", new TemplateParserContext())`: the string is a template; only the part inside the delimiters is evaluated.

Template expressions are suited for content with a relatively stable structure that needs dynamic values inserted, such as notifications, labels, or descriptive messages. If the string is only a simple configuration value, a placeholder is usually enough. If the content needs localization, number/date formatting, or complex display rules, consider a dedicated message/template mechanism instead of packing everything into one long expression.

## 7. Quick Comparison

| Criterion | Java code | Property placeholder `${...}` | SpEL `#{...}` | SpEL template expression |
|---|---|---|---|---|
| Purpose | Execute application logic | Retrieve configuration value by key | Evaluate expression on data/context | Build a string from text and expressions |
| Timing | At runtime; compiled code | When Spring resolves configuration/bean values | When Spring or the application evaluates the expression | When the parser evaluates the template |
| Data type | Explicit Java types | Usually starts as a string configuration value then converted | Can return various types depending on the expression | Usually used to produce strings |
| Object access | Via Java variables, fields, methods | Does not access objects on its own | Yes, depending on the evaluation context | Yes, inside each SpEL segment |
| Computation | Yes | Not a placeholder's function | Yes | Yes, inside SpEL segments |
| Refactoring/type checking | Well supported by compiler and IDE | Configuration keys require separate management | Dynamic strings have less refactoring/type support | Similar to SpEL |
| Common locations | Services, domain classes, helpers, configuration classes | `@Value`, Spring configuration | `@Value`, bean definitions, rules, or SpEL-enabled APIs | String content needing dynamic value interpolation |

## 8. Choosing the Right Tool

You can decide based on the question you need to answer:

1. **“What is the configuration value of this key?”** Use `${...}`. For example: `@Value("${app.api-url}")`.
2. **“I need to compute or read data from an object in a configuration point that supports expressions.”** Use SpEL. For example: `@Value("#{systemProperties['user.timezone']}")`.
3. **“I need a fixed string with dynamic data inserted.”** Use a template expression. For example: `"Hello #{#customer.name}"` with `TemplateParserContext`.
4. **“This is a business rule or multi-step logic.”** Write Java code, place the logic in a clearly named class/method, and test it like regular code.

A practical rule: configuration should describe values; expressions should be short and readable; business logic should have a clear name and location in Java. SpEL is very convenient at configuration boundaries or when dynamic data evaluation is needed, but expression strings should not be turned into a place holding the entire behavior of the application.

## 9. Common Confusions

- **Using the wrong delimiters:** `${app.name}` is a placeholder; `#{...}` marks SpEL in Spring configuration. The two syntaxes cannot be swapped arbitrarily.
- **Forgetting the context:** `#order` only works if the `order` variable is placed in the evaluation context. `order.total` only works if the root object or context can resolve that name.
- **Confusing a raw expression with a template:** the default parser treats the entire string as an expression. To preserve outer text and evaluate `#{...}` segments, you must use a template parser context.
- **Expecting placeholders to compute:** `${app.a * 2}` is not a multiplication expression. Pass the value into SpEL or compute it in Java.
- **Hiding overly long logic in annotations:** multi-layered expressions make configuration hard to read and hard to test. Move complex logic to a Java method whose name describes its purpose.
- **Evaluating untrusted expressions:** `StandardEvaluationContext` can provide property, method, and type access depending on configuration. Do not evaluate SpEL strings submitted by untrusted users. For restricted data binding needs, consider `SimpleEvaluationContext` and enable only the capabilities actually needed.

## 10. Takeaways

- Java code is the default choice for structured application logic that needs type control.
- `${...}` retrieves values from configuration by key.
- SpEL evaluates expressions against the root object, variables, and components provided in the evaluation context.
- `#{...}` is how Spring configuration marks a SpEL segment; the parser API usually takes a plain expression.
- Template expressions preserve literal text and evaluate the SpEL segments between the prefix and suffix.
- Placeholders and SpEL can be combined: placeholders bring configuration values in, and SpEL performs calculations or accesses data.
