# Expression Formatting in Configuration Strings

SpEL often appears inside Spring configuration strings: values injected with @Value, attributes in XML, or strings parsed by the application itself. In such cases, it is necessary to distinguish two scenarios: the entire string is a SpEL expression, or the string has fixed text interspersed with expression segments. The second scenario is called a template expression.

Parsing a template string requires additional information about delimiters. SpEL provides TemplateParserContext for this purpose. In Spring, integrations such as @Value also have their own mechanisms for recognizing expressions by convention. Understanding this configuration class properly helps avoid confusing placeholder syntax with SpEL and avoid evaluating a string at the wrong time.

## 1. Two common string forms

### 1.1. String containing only a single expression

When the entire input is an expression, the parser receives the expression directly:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(12, 30)"
);

Integer result = expression.getValue(Integer.class);
~~~

Here the input string is pure SpEL syntax. There is no need to wrap the expression in #{...} when calling parseExpression(String) directly.

In Spring, @Value can use expression syntax:

~~~java
@Value("#{T(java.lang.Math).max(12, 30)}")
private int pageSize;
~~~

The #{...} syntax is the convention Spring uses to recognize the SpEL part inside an annotation value. It does not mean every call to parseExpression(String) automatically strips these delimiters.

### 1.2. Fixed text interspersed with expressions

Sometimes the result needs to be a complete string containing both text and dynamic data, for example:

~~~text
Order 1024 has a total amount of 250000.
~~~

Instead of concatenating strings manually in Java, you can write a template:

~~~text
Order #{#root.orderNumber} has a total amount of #{#root.total}.
~~~

The parser needs to know which segments are ordinary text and which segments should be evaluated as SpEL. TemplateParserContext provides the opening and closing delimiter convention for those segments.

## 2. TemplateParserContext and default delimiters

TemplateParserContext is a ParserContext intended for template mode. The default constructor uses:

- Prefix: #{
- Suffix: }

All content between the delimiter pair is treated as a SpEL expression. Content outside those segments is preserved as fixed text.

Complete example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(1024L, new BigDecimal("250000"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Expression template = parser.parseExpression(
        "Order #{#root.orderNumber} has a total amount of #{#root.total}.",
        new TemplateParserContext()
);

String message = template.getValue(context, String.class);
~~~

In this example, the parser builds a template expression consisting of several parts: the text before the first expression, the orderNumber value, the text in the middle, the total value, and the final period. When getValue is called, the SpEL segments are evaluated using the provided EvaluationContext, then combined with the fixed text into the result.

If you only call parseExpression(String) without passing TemplateParserContext, a string containing text like the example above is not interpreted in template mode. Pass ParserContext explicitly when manually parsing a string that has multiple text and expression parts.

## 3. A template can contain multiple expressions

A template string can contain one or more SpEL segments. The segments are evaluated in the same evaluation environment, so they can share the root object, variables, and capabilities configured in EvaluationContext.

~~~java
String source =
        "Customer #{#root.customer.name} ordered "
        + "#{#root.lines.size()} items, total amount "
        + "#{#root.total}.";

Expression template = parser.parseExpression(
        source,
        new TemplateParserContext()
);

String summary = template.getValue(context, String.class);
~~~

Each segment inside the delimiter pair is a separate expression. The text between segments is kept intact. This is suitable for notifications, display labels, descriptions, or configuration content that needs a few dynamic values inserted.

Keep each expression segment short and readable. If a segment requires multiple conditional branches or lengthy business calculations, consider moving that logic into a clearly named method or preparing the data on the input object beforehand. A template should express how the result is presented, not become a place containing all business logic.

## 4. Using custom delimiters

If a configuration string already uses #{ or } for another purpose, you can choose a different delimiter pair using the TemplateParserContext constructor.

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
        "Hello [[#root.displayName]], your code is [[#root.code]].",
        parserContext
);

String message = template.getValue(context, String.class);
~~~

In this example, only the content between [[ and ]] is parsed as an expression. The remaining text is kept as-is.

Custom delimiters are useful when templates are stored in configuration files or shared with another system that already has its own character convention. Choose a delimiter pair that rarely appears in ordinary text, keep it consistent between where the template is authored and where it is parsed, and document that convention clearly in configuration documentation.

ParserContext only describes how the parser splits the string into text and expressions. It does not grant data access permissions and does not replace EvaluationContext. When evaluating the template, you still need to supply the appropriate root object, variables, and resolvers.

## 5. Distinguishing ParserContext from EvaluationContext

These two names often appear side by side, but they are responsible for two different moments in time:

| Component | Question it answers | Example |
|---|---|---|
| ParserContext | Which part of the string is an expression, and which part is text? | TemplateParserContext with prefix #{ and suffix } |
| EvaluationContext | When running the expression, what data can be seen and what capabilities can be invoked? | StandardEvaluationContext with root object, variables, and accessors |

You can visualize the sequence as follows:

~~~text
Configuration string
      |
      v
ExpressionParser + ParserContext
      |
      v
Parsed Expression / template
      |
      v
getValue(EvaluationContext)
      |
      v
Resulting text
~~~

ParserContext does not know who the current order object or user is. EvaluationContext does not decide which delimiters are used to identify expression segments in the input string. Separating these two responsibilities makes diagnosing errors easier: template recognition errors usually lie in the parser or ParserContext; missing property, variable, or bean errors usually lie in EvaluationContext.

## 6. Expressions in Spring configuration strings

Spring provides integration points capable of processing SpEL. A common example is @Value.

### 6.1. Dynamic values in @Value

~~~java
@Component
public class RuntimeInfo {

    @Value("#{systemProperties['java.version']}")
    private String javaVersion;

    @Value("Running Java version: #{systemProperties['java.version']}")
    private String description;
}
~~~

The first field receives the value of the expression. The second field illustrates a string with fixed text interspersed with an expression. Spring processes the expression during bean creation and injection.

An expression can be used to compute a value:

~~~java
@Value("#{T(java.lang.Math).max(10, 20)}")
private int limit;
~~~

The result of the expression is converted to the target type if Spring's conversion mechanism supports it. Choose a field or parameter type that matches the actual result.

### 6.2. Placeholders and SpEL are two different mechanisms

Spring also supports placeholders to retrieve values from configuration. For example in application.properties:

~~~properties
app.name=Order Service
app.max-items=50
~~~

These values can be injected using placeholders:

~~~java
@Value("${app.name}")
private String applicationName;

@Value("${app.max-items}")
private int maxItems;
~~~

Placeholders use the dollar sign and curly braces to reference configuration properties. SpEL uses the # sign and curly braces to represent expressions. The two syntaxes serve different purposes:

| Syntax | Meaning | Example |
|---|---|---|
| ${...} | Look up properties in Environment/property sources | ${app.name} |
| #{...} | Parse and evaluate a SpEL expression at a supported Spring integration point | #{T(java.lang.Math).max(10, 20)} |

Do not assume that every value in application.properties or application.yml containing #{...} will automatically be evaluated. SpEL evaluation depends on the Spring component reading that value. For example, reading a string via Environment.getProperty(...) does not mean asking Spring to execute that string as an expression.

When a value needs both a placeholder and SpEL, clearly determine the resolution order at the integration point being used and verify the result with a small configuration test. Avoid concatenating configuration strings into expression code when data can be passed via variables or the root object.

### 6.3. Configuration strings in XML

Spring XML configurations can also use SpEL in attributes where the container supports expressions:

~~~xml
<bean id="runtimeInfo" class="example.RuntimeInfo">
    <property name="javaVersion"
              value="#{systemProperties['java.version']}" />
</bean>
~~~

Distinguish XML syntax from SpEL syntax inside the attribute value. XML follows XML escaping rules; expression content follows SpEL syntax rules. If a string contains special characters, handle them properly at both layers.

### 6.4. YAML values and evaluation timing

YAML merely formats configuration data. A string like the following is by itself still a text value:

~~~yaml
app:
  welcome-template: "Hello #{#root.displayName}"
~~~

Reading this string from Environment does not automatically create a SpEL template. If you want to evaluate it, the application must proactively pass the string to ExpressionParser with TemplateParserContext and provide an appropriate EvaluationContext, or use a Spring integration point that supports SpEL according to that point's contract.

This is an important difference between storing a string with expression-like markers and actually asking a component to evaluate an expression.

## 7. Quotes and escaping layers

An expression can reside simultaneously inside multiple syntax layers: Java, XML, YAML, properties, and SpEL. Each layer has its own escaping rules.

### 7.1. String literals inside SpEL

SpEL uses single quotes for string literals:

~~~text
#{'Hello'}
#{#root.name == 'admin'}
~~~

If the expression is written inside a Java String, double quotes delimit the Java string while single quotes can remain as-is for SpEL:

~~~java
String source = "Username: #{#root.name}";
~~~

If the expression content needs double quotes or backslashes, escape them according to Java syntax before the string reaches the parser. When placed in XML or YAML, continue following the escaping rules of the respective format.

### 7.2. Do not assume one backslash handles every layer

A character may need escaping at the outer layer yet have a different meaning at the inner layer. For example, a double quote can be an XML attribute delimiter, a character in a Java string, or a character in the expression content. Determine the actual string that ExpressionParser receives before concluding that SpEL syntax is wrong.

For templates whose text content contains the delimiter pair itself, do not assume that adding a backslash always has the same escaping effect across every parser or every version. If delimiters conflict with content, consider choosing custom delimiters or concatenating the fixed text outside the template.

## 8. Separating dynamic data from the expression string

Do not insert user-entered data directly into expression content via string concatenation. For example, concatenating a username into a SpEL segment can cause the data to be misinterpreted as syntax.

Instead, keep the expression fixed and pass data via the root object or variables:

~~~java
Expression expression = parser.parseExpression(
        "Hello #{#displayName}",
        new TemplateParserContext()
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("displayName", userSuppliedName);

String message = expression.getValue(context, String.class);
~~~

With this approach, userSuppliedName is data passed into the context, not part of the expression code. This prevents quote errors, syntax errors caused by input, and reduces the risk of expressions being altered unexpectedly.

If expressions are stored in a database or configuration file that could be edited by untrusted parties, treat that content as executable code. Restrict the root object, accessors, methods, and resolvers strictly as needed. Prefer SimpleEvaluationContext for limited data binding; only use a full context when the feature requires it and the expression source is controlled.

## 9. Parse once, evaluate per data item

For stable configuration templates, parse the string once when initializing the configuration or component, then reuse the Expression for multiple evaluations where appropriate. Each evaluation can pass a root object or context containing that call's data.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression messageTemplate = parser.parseExpression(
        "Order #{#root.id} has status #{#root.status}.",
        new TemplateParserContext()
);

String render(Order order) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    return messageTemplate.getValue(context, String.class);
}
~~~

This organization avoids repeatedly parsing the same configuration string. At the same time, the context is created per render call's data so it does not accidentally reuse the previous request's root object.

If configuration can change at runtime, clearly define when to reload and re-parse the template. When the parser reports an error, record the configuration name or source location so operators know which string is invalid; avoid logging sensitive data that was injected into the expression or result.

## 10. Common errors and how to handle them

| Symptom | Common cause | How to check |
|---|---|---|
| String has #{...} but is not substituted | Reading the string as an ordinary configuration value | Check which component actually invokes the SpEL parser |
| Template reports a syntax error | Using parseExpression(String) for a string with text interspersed with expressions | Pass TemplateParserContext or an appropriate ParserContext |
| Property not found in template segment | Root object or EvaluationContext lacks the required data | Check root object, property names, and accessors |
| Variable not found | Expression uses #name but the context has not set that variable | Check setVariable and variable name spelling |
| Result is not the expected type | Expression value differs from target type or cannot be converted | Check getValue with result type and converter |
| Text containing delimiters is misparsed | Literal content conflicts with prefix/suffix | Choose different delimiters or concatenate literal parts externally |
| Placeholder is not substituted | Property source or placeholder configurer is not configured | Check property sources and placeholder resolution mechanism |

When debugging, separate two steps: first confirm that the parser creates an Expression from the string; then confirm that getValue evaluates properly with the actual context and data. If using a Spring integration, check that integration's rules rather than assuming it behaves like a manual parser call.

## 11. Design rules for configuration strings with SpEL

- Use plain expressions when the entire value is a single calculation or dynamic value.
- Use TemplateParserContext when the string has fixed text interspersed with expression segments.
- Keep delimiters consistent; only customize prefix/suffix when the format contains the default delimiters.
- Distinguish property placeholders from SpEL and rely only on mechanisms supported at the integration point.
- Keep expressions short and readable, and avoid embedding complex business logic in strings.
- Pass data through the root object or variables; do not concatenate user input into expression code.
- Configure EvaluationContext with minimal privileges and do not evaluate untrusted strings with a full context.
- Parse stable configurations once and handle parse errors explicitly at startup or when reloading configuration.

## 12. Key takeaways

A configuration string can be a pure SpEL expression or a template consisting of fixed text and multiple expression segments. When parsing a template manually, TemplateParserContext defines the prefix/suffix; EvaluationContext provides the necessary data and capabilities at evaluation time. In Spring, @Value and some other integration points can process SpEL according to their own conventions, whereas reading a regular property does not automatically mean evaluating SpEL.

Always identify who parses the string, which delimiters are used, which data is supplied at runtime, and whether the configuration source is trustworthy. When those four things are clear, expressions in configuration will be easy to read, easy to maintain, and unlikely to cause surprises during deployment.