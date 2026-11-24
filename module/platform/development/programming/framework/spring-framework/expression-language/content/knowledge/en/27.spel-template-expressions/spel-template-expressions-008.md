# Controlling Data Inserted into Resulting Strings in SpEL Template Expressions

SpEL Template Expressions allow combining fixed text with expressions evaluated at runtime. For instance, a template can generate a greeting from a username or build a notification from an order status. When data is inserted into the resulting string, you need to control the expression source, runtime values, and where the resulting string will be used.

Template expressions only substitute the parts marked by the parser's delimiters. They do not sanitize data automatically, do not auto-escape HTML, SQL, JavaScript, or URLs, and do not make an untrusted template safe. Keep template structures in code or approved sources, pass data through strongly typed variables, and encode output according to the usage context.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Understand how TemplateParserContext separates fixed text and expression parts.
- Build a resulting string from multiple literal segments and runtime values.
- Pass data via variables instead of concatenating input into the expression source.
- Distinguish expression injection from inserting a normal data value.
- Understand that template expressions do not automatically escape or encode output.
- Choose appropriate encoding for HTML, URL, JavaScript, JSON, SQL, CSV, and logs.
- Handle nulls, data types, locale, timezone, and output length.
- Restrict EvaluationContext and template sources.
- Test strings containing delimiters, special characters, and malicious payloads.

You should know SpelExpressionParser, Expression, EvaluationContext, variables prefixed with #, and how an application outputs strings to another system.

## 2. How Do Template Expressions Work?

A regular expression is parsed as a complete SpEL expression. Template expressions allow mixing plain text with SpEL segments enclosed between delimiters.

By default, TemplateParserContext uses the opening #{ prefix and closing } suffix.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "Hello, #{#name}!",
    new TemplateParserContext()
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");

String message = expression.getValue(context, String.class);
~~~

Result:

~~~text
Hello, An!
~~~

The parser preserves Hello, and ! as literal text; the #name part inside delimiters is evaluated as an expression. The results of all parts are concatenated into one string.

A template can contain multiple expression segments:

~~~text
Order #{#order.number} has status #{#order.status}.
~~~

Each segment is evaluated in the same EvaluationContext, and results are combined in order of appearance.

### 2.1. Template Structure and Runtime Values Are Two Different Things

Suppose the fixed template is:

~~~text
Welcome, #{#displayName}.
~~~

The displayName value is passed via context. If that value contains characters such as #{, }, quotes, or strings resembling SpEL syntax, it remains just a variable value in the current evaluation. SpEL does not recursively parse string content returned from a variable as a new template.

Risk arises when an application concatenates untrusted data into the template source and then parses the concatenated string. At that point, input can become SpEL syntax rather than mere data.

## 3. Keep Templates Fixed, Pass Data via Variables

The recommended practice is to parse a template controlled by the application, then pass dynamic values through EvaluationContext.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Customer #{#customerName} has #{#itemCount} items.",
    new TemplateParserContext()
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", customerName);
context.setVariable("itemCount", itemCount);

String output = template.getValue(context, String.class);
~~~

Expression structure does not change with input data. Variable names and data types are explicitly defined in code.

Avoid doing the following:

~~~java
String source =
    "Customer " + userInput + " is active";

Expression expression = parser.parseExpression(source);
~~~

In this example, userInput becomes part of the source processed by the parser. If the string contains valid SpEL syntax, it can alter the expression's meaning or trigger capabilities of EvaluationContext.

If arbitrary data must be inserted, keep the data in a variable:

~~~java
Expression template = parser.parseExpression(
    "Customer #{#customerName} is active",
    new TemplateParserContext()
);

context.setVariable("customerName", userInput);
~~~

The userInput value is now processed as data supplied to a fixed expression, not new source code.

## 4. Distinguishing Expression Injection from Output Injection

These are two distinct risks:

| Risk | Where does it happen? | Primary mitigation |
|---|---|---|
| Expression injection | Untrusted input is placed into SpEL source and parsed/evaluated | Do not concatenate input into source; use only approved templates and restricted contexts |
| Output injection | Resulting string is placed into HTML, JavaScript, URL, SQL, logs, or other formats without context-appropriate encoding | Encode or serialize at the data output point according to the exact context |

Keeping the template fixed and passing variables prevents input data from becoming SpEL syntax. However, that alone does not guarantee the resulting string is safe when a browser or another system processes it.

For example, a username might contain:

~~~text
<script>alert(1)</script>
~~~

If this value is inserted into a template and rendered directly as HTML, the browser may interpret it as markup or script. SpEL does not automatically know the string is being used as HTML and does not encode special characters.

Therefore, protection is needed at both boundaries: the expression source and the output sink.

## 5. Template Expressions Do Not Auto-Escape Data

The SpEL template parser only evaluates expression parts and combines results with literal text. It is not an HTML template engine with context-aware auto-escaping.

Example:

~~~text
<p>Hello, #{#name}</p>
~~~

If name contains HTML markup, the result still contains that content. When returning results to a browser, encode the data for the HTML text context or use a template engine/framework with properly configured auto-escaping.

Do not use a single generic escape function for every output type. HTML text, HTML attributes, JavaScript strings, CSS, URL components, and JSON all have different rules.

### 5.1. Encode at the Point of Use

A string may be built in the service layer and then used in multiple different contexts. Hence, it is usually best to keep data values unencoded in the model and encode at the output destination.

For example:

- When rendering in HTML, use HTML escaping suitable for text or attribute context.
- When placing into a URL query parameter, URL-encode the parameter value individually.
- When generating JSON, use a JSON serializer instead of manually concatenating braces and quotes.
- When rendering in JavaScript, avoid manual string concatenation; use a safe data serialization mechanism.
- When logging, use structured logging and handle newline characters to prevent log injection.

Encoding too early can cause double-encoding when the string is used in another context. Identify the output sink and apply the right encoder at that boundary.

## 6. Do Not Build SQL Queries with Template Expressions

Do not use SpEL templates to concatenate data into SQL and then execute the resulting string.

Unsafe design example:

~~~text
SELECT * FROM account WHERE username = '#{#username}'
~~~

If the resulting string is sent directly to JDBC as complete SQL, data can alter the query's structure.

Use PreparedStatement or the parameter binding mechanism of Spring JDBC/JPA:

~~~java
jdbcTemplate.query(
    "select * from account where username = ?",
    rowMapper,
    username
);
~~~

Template expressions can suit generating display content or messages, yet they do not replace parameterized queries. SQL identifiers such as table names or column names cannot be protected solely by binding values either; if dynamic identifier selection is required, use an allowlist in Java.

## 7. Do Not Build Shell Commands or Source Code from Data

Do not use template expressions to concatenate untrusted data into shell commands, scripts, Java source, or content that will be evaluated as code in a subsequent step.

Example:

~~~text
run-command --user "#{#username}"
~~~

If the resulting string is passed straight to a shell, quotes or control characters in username can alter how the shell parses the command.

A safer way is to invoke an API/process with a separate argument list, bypassing a shell, and validate each argument against its contract. For source code or nested expressions, use a dedicated parser/serializer and a narrow language allowlist; do not re-parse the resulting string merely because it looks syntactically valid.

## 8. Restricting EvaluationContext

Even when a template is fixed, inner expressions can still access whatever EvaluationContext permits.

A broad context may expose:

- Properties and fields on the root object.
- Variables holding services or mutable objects.
- Method invocation.
- Type references via T(...).
- Constructor invocation.
- Bean references via @beanName.
- Property assignment or capabilities with side effects.

For templates needing only to interpolate a few fields, provide a small DTO and a read-only context:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("customerName", customerName);
context.setVariable("itemCount", itemCount);
~~~

Do not place ApplicationContext, BeanFactory, repositories, administrative services, or large entity graphs into the context just to fetch a single value. If expressions need methods, expose a small facade with pure methods and restrict resolvers explicitly.

SimpleEvaluationContext is not an absolute sandbox; provided data and accessors still must be controlled. Select capabilities according to the template's genuine needs.

## 9. Using Custom Delimiters When Needed

TemplateParserContext lets you specify custom prefix and suffix:

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
    "Hello [[#name]]!",
    parserContext
);
~~~

In the example, the expression segment is placed between [[ and ]]. Custom delimiters can be useful when literal text frequently contains #{ or when integrating with another template format.

Choose delimiters unlikely to appear naturally in content. Document this convention in configuration and test cases where delimiters appear in text. Do not change delimiters as a substitute for controlling template sources; an untrusted template can still contain the new delimiters.

If a template must pass through multiple processing layers, avoid sharing delimiters with another tool if that causes misparsing or makes it hard to tell which layer owns the syntax.

## 10. Handling Nulls and Default Values

If a property or variable may be null, clearly decide which string should appear in the output.

Example:

~~~text
Hello, #{#customer?.displayName ?: 'Guest'}.
~~~

Safe navigation protects the property when customer is null; Elvis supplies the default value if the result is null.

You can use a default value for counts:

~~~text
You have #{#itemCount ?: 0} items.
~~~

Only use defaults when null genuinely means using that value. If null indicates missing mandatory data, validate and report an error rather than silently replacing it with a default string.

Do not rely on how a null value gets converted into a string. Write Elvis explicitly or handle nulls in Java so results have consistent meaning.

## 11. Controlling Data Types and Formatting

Template expressions can insert Strings, Numbers, Booleans, dates/times, or method results. How values convert to strings can affect displayed content.

For data requiring specific formatting:

- Currency: define currency, scale, and rounding before generating content.
- Decimals: specify decimal separator and locale.
- Date/time: specify timezone and format, without relying on server defaults.
- Booleans and enums: choose stable display labels instead of relying on technical names if end users read the output.
- Collections: limit element count and define separators.
- Custom objects: use an explicit property or formatter instead of relying on default toString().

Example normalizing values beforehand in Java and passing them into context:

~~~java
context.setVariable("formattedTotal", moneyFormatter.format(total));
context.setVariable("formattedDate", dateFormatter.format(createdAt));
~~~

The template handles only combining the prepared values:

~~~text
Total: #{#formattedTotal}; created at #{#formattedDate}
~~~

This separates formatting logic from sentence structure and allows testing formatters independently.

## 12. Controlling Length and String Construction Cost

Templates can insert large content or invoke resource-intensive expressions. If input data is unbounded, a seemingly simple notification can produce a huge string or consume excessive runtime.

Make sure to:

- Limit the length of input data.
- Limit the number of collection elements passed into the template.
- Avoid invoking methods that perform I/O or unbounded queries in templates.
- Keep expressions small, avoiding projections over large collections when unnecessary.
- Limit template size and number of expression segments at the policy management layer.
- Use appropriate timeouts/resource limits at the application layer when expensive processing occurs.
- Never treat length limits as a replacement for capability allowlists.

If you need to render large reports, complex emails, or HTML pages, use a dedicated templating tool with proper escaping, layout, and resource limit management.

## 13. Parse Once, Evaluate per Current Context

If a template is fixed and used many times, parse it once and evaluate with a separate context per processing call.

~~~java
Expression template = parser.parseExpression(
    "Order #{#orderNumber}: #{#status}",
    new TemplateParserContext()
);

String render(String orderNumber, String status) {
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("orderNumber", orderNumber);
    context.setVariable("status", status);

    return template.getValue(context, String.class);
}
~~~

The template structure can be reused; the context holding runtime data should be created or scoped to each rendering call.

Do not share a mutable EvaluationContext across concurrent requests and overwrite variables. Doing so can cause one request's data to appear in another request's output.

If templates are stored via configuration, cache Expressions by template ID and version. When content changes or is revoked, invalidate the corresponding cache entry. Do not cache rendered strings across users if cache keys do not fully reflect relevant data and permissions.

## 14. Testing Data Inserted into Templates

Test both resulting content and how the output is used:

| Case | Data | What to verify |
|---|---|---|
| Normal value | name = An | Interpolated in the right position |
| Value containing delimiters | name contains #{...} | Value is not recursively parsed |
| Quotes and backslashes | name has quote/backslash | Interpolation does not break template |
| HTML markup | name contains script tags | Output is HTML-encoded at sink |
| URL characters | value has spaces and & | Parameter is properly URL-encoded |
| Null | customer = null | Safe navigation/default works as designed |
| Missing property | Wrong property name | Error is detected rather than turning into allow |
| Overly long input | String exceeds limit | Rejected per clear policy |
| Untrusted template | Content has arbitrary expressions | Not published/evaluated unless approved |
| Broad context | Variable holds service | Test confirms runtime context exposes no unnecessary capabilities |
| Multiple requests | Two different variable sets | Results do not mix data |

In addition to unit tests for expressions, test at the actual output point: HTML renderer, URL builder, JSON serializer, or logging framework. String safety can only be fully assessed when the final sink is known.

## 15. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
|---|---|---|
| Input alters expression syntax | Data concatenated into source before parsing | Keep template fixed and pass input via variables |
| Value containing #{...} treated as code | Application re-parses resulting string as a new template | Do not recursively parse data content |
| HTML executes or renders unexpectedly | Template expressions do not auto-escape HTML | Encode per HTML context at output sink |
| SQL is altered | Using template string as executable SQL query | Use PreparedStatement or parameter binding |
| URL is broken or manipulable | Inserting value without encoding parameter | Use URI builder and encode each parameter |
| Null appears unexpectedly | No explicit default defined | Use Elvis or handle null in Java |
| Template fails to parse delimiters accurately | Delimiter overlaps literal content or another tool | Choose appropriate parser context/delimiters and test |
| Data mixes across requests | Sharing a mutable context | Create a separate context for each render |
| Resulting string is too large | Input or collection is unbounded | Limit size and element count |
| Expression invokes unintended methods | EvaluationContext has overly broad resolvers | Use a narrow context and allowlisted facade |

## 16. Practice Exercises

1. Create template Hello, #{#name}! and evaluate with two different name values.
2. Pass a value containing the string #{T(java.lang.Math).PI} via a variable; verify that content is inserted as data, not re-parsed.
3. Try concatenating input directly into expression source in an isolated test to understand the expression injection boundary.
4. Create a template with a null customer and use safe navigation with Elvis.
5. Try custom delimiters using TemplateParserContext.
6. Render a name containing HTML markup and then encode it at the HTML output sink.
7. Build URL query parameters using a URI builder instead of manual string concatenation.
8. Use PreparedStatement for queries with user data instead of building SQL with templates.
9. Create two separate EvaluationContexts and verify data does not mix between two renders.
10. Limit input length and collection element count and verify behavior when limits are exceeded.

## 17. Checklist Before Inserting Data into Resulting Strings

- [ ] Does the template come from a trusted source and have version management?
- [ ] Is dynamic data passed via variables instead of concatenated into the expression source?
- [ ] Is recursive parsing of the resulting string avoided?
- [ ] Does EvaluationContext expose only the required root object, variables, and capabilities?
- [ ] Are nulls and default values clearly defined?
- [ ] Has the final output sink been identified?
- [ ] Is data encoded according to the exact HTML/attribute/URL/JavaScript context?
- [ ] Is a JSON serializer used instead of manual JSON concatenation?
- [ ] Is parameter binding used instead of building SQL with templates?
- [ ] Is placing the resulting string directly into shells or source code avoided?
- [ ] Are locale, timezone, and data formats clear?
- [ ] Are template length, input length, and collection sizes bounded?
- [ ] Are contexts isolated across concurrent requests?
- [ ] Have delimiters, quotes, markup, nulls, and special payloads been tested?

## 18. Conclusion

Template expressions combine literal text with SpEL segments marked by delimiters, defaulting to #{ and }. Keep templates in trusted sources, pass data through variables, and avoid concatenating input into expression sources or re-parsing resulting strings. SpEL does not auto-escape output: HTML, URL, JavaScript, JSON, SQL, shell, and logs all require dedicated handling at the point of use. Restrict EvaluationContext, handle nulls/formatting explicitly, enforce size limits, and test both the expression boundary and output sink so the resulting string never alters the meaning of the receiving system.