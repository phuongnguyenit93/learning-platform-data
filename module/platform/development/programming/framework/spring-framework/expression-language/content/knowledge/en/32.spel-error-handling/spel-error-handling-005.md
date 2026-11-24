# Position Information in Failing Expressions

## 1. Why Do We Need Error Position?

When SpEL cannot parse or evaluate an expression, the error message usually indicates the kind of problem. The error position helps pinpoint the part of the source that needs inspection.

Examples:

    customer.address.city
    orders[10].total
    T(java.lang.Math).max(, 5)
    #normalizeCode(#region

Errors can originate from invalid syntax, a missing property, a `null` intermediate object, a missing method, an out-of-bounds index, or a failed type conversion.

Spring Expression Language provides exceptions containing information such as:

- The expression string related to the error, if the exception stores that information.
- The position where the error occurred in the expression.
- The error message code and insert values for SpEL-specific exceptions.
- The root cause if the error is wrapped from another exception.

This information supports logging, displaying configuration errors, and debugging. However, the position is a marker provided by the parser or node evaluation; it is not always an exact source range covering the entire error.

## 2. Two Phases Where Errors Can Occur

Using SpEL typically has two separate phases:

1. Parsing: `ExpressionParser` analyzes the source and creates an `Expression`.
2. Evaluation: `Expression` evaluates against an `EvaluationContext` and a root object.

The two phases have different exception types:

| Phase | API | Base Exception | Error Examples |
| --- | --- | --- | --- |
| Parsing | parser.parseExpression(...) | ParseException | Missing brackets, invalid token, unclosed string |
| Evaluation | expression.getValue(...) | EvaluationException | Unreadable property, method not found, null reference, conversion error |

Example:

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("customer.address.city");

    Object city = expression.getValue(context);

If the source has invalid syntax, the error occurs at `parseExpression` and there is no valid `Expression` to evaluate.

If the source is valid but `customer.address` is `null`, parsing still succeeds. The error only appears when `getValue` accesses the object at runtime.

Distinguishing the two phases helps select the right exception to handle and avoids looking for runtime errors in the parser when the source already parsed successfully.

## 3. ExpressionException and getPosition()

Both `ParseException` and `EvaluationException` extend `ExpressionException`.

Important APIs:

| API | Meaning |
| --- | --- |
| getExpressionString() | The expression source attached to the exception; may be null |
| getPosition() | Position in the expression where the issue occurred |
| getMessage() | Detailed message; equivalent to toDetailedString() |
| getSimpleMessage() | Short message, without the expression source |
| toDetailedString() | Detailed description including source and position if available |

Example:

    try {
        parser.parseExpression("customer.address.city");
    }
    catch (ExpressionException ex) {
        String source = ex.getExpressionString();
        int position = ex.getPosition();

        System.out.println(ex.getSimpleMessage());
        System.out.println(ex.toDetailedString());
    }

`getPosition()` returns a numeric position in the source expression. This position is an offset in the Java string, not directly a line and column number.

In the parser implementation, the position is calculated by `String` character index. When displaying to users, the application can convert that offset into line/column. Remember that Java `String` uses UTF-16 code units; Unicode characters outside the Basic Multilingual Plane can occupy two `char` positions.

Not every exception has a useful source or position. `ExpressionException` uses `-1` to represent an unknown position in cases where a source exists but the position is unknown. Some exceptions are created without an attached expression string. Check both source and position before building a marker.

## 4. SpelParseException: Errors During Parsing

`SpelParseException` is a SpEL-specific exception that extends `ParseException`.

It stores:

- A `SpelMessage` code describing the error type.
- `inserts` containing additional values for the message.
- Position and expression source via `ExpressionException`.

Example:

    try {
        parser.parseExpression("T(java.lang.Math).max(, 5)");
    }
    catch (SpelParseException ex) {
        System.out.println(ex.getMessageCode());
        System.out.println(Arrays.toString(ex.getInserts()));
        System.out.println(ex.getPosition());
        System.out.println(ex.getExpressionString());
    }

The error code can indicate that the parser encountered an unexpected token, a missing character, a missing argument, or an unterminated string literal.

If using a template `ParserContext`, some delimiter structure errors are created as a general `ParseException` rather than `SpelParseException`. Therefore, when handling parsing errors at the API level, catch `ParseException`; only read `getMessageCode()` and `getInserts()` when the exception is actually a `SpelParseException`.

## 5. SpelEvaluationException: Errors During Evaluation

`SpelEvaluationException` is a SpEL-specific exception that extends `EvaluationException`.

It also stores a `SpelMessage` code and `inserts` that help identify the error. The position is usually tied to the node in the expression performing the failing operation.

Example:

    try {
        Expression expression =
            parser.parseExpression("customer.address.city");

        expression.getValue(context);
    }
    catch (SpelEvaluationException ex) {
        System.out.println(ex.getMessageCode());
        System.out.println(Arrays.toString(ex.getInserts()));
        System.out.println(ex.getPosition());
        System.out.println(ex.getCause());
    }

Some evaluation scenarios that can occur:

- Property does not exist or cannot be read.
- Property is accessed on a `null` object.
- Method is not found or cannot be invoked.
- Function is not registered.
- Index is out of bounds.
- Data type cannot be converted.
- Bean reference has no `BeanResolver` or bean lookup fails.
- Constructor does not match the arguments.

Not every `EvaluationException` is a `SpelEvaluationException`. If using a custom resolver or custom integration code, the application may receive a general `EvaluationException`. In that case, use the superclass API and inspect the cause.

## 6. getMessageCode() and getInserts()

`SpelParseException` and `SpelEvaluationException` do not merely hold a fixed message string. They store a `SpelMessage` code and values inserted into the message.

Examples of some codes:

| SpelMessage Code | Meaning |
| --- | --- |
| TYPE_NOT_FOUND | Referenced type not found |
| PROPERTY_OR_FIELD_NOT_READABLE | Property or field cannot be read |
| METHOD_NOT_FOUND | Matching method not found |
| FUNCTION_NOT_DEFINED | Function not registered |
| CANNOT_INDEX_INTO_NULL_VALUE | Cannot index into null |
| COLLECTION_INDEX_OUT_OF_BOUNDS | Collection index out of bounds |
| TYPE_CONVERSION_ERROR | Type conversion failed |
| NO_BEAN_RESOLVER_REGISTERED | Context has no BeanResolver |
| CONSTRUCTOR_NOT_FOUND | Matching constructor not found |

For example, when a property cannot be read, `inserts` may contain the property name and object type. For an index error, `inserts` may contain the collection size and requested index.

Use the error code to classify and handle programmatically:

    if (ex.getMessageCode() ==
            SpelMessage.PROPERTY_OR_FIELD_NOT_READABLE) {
        // Handle unreadable property error
    }

Do not classify errors by comparing `getMessage()` verbatim. Message content can change across versions or locales, whereas `SpelMessage` provides a clearer identifier.

`getInserts()` is supplementary data to explain the error. Do not assume that every error code has the same count or types of inserts.

## 7. getMessage(), getSimpleMessage(), and toDetailedString()

These three APIs serve different purposes.

    ex.getMessage()
    ex.getSimpleMessage()
    ex.toDetailedString()

`getMessage()` returns the detailed form, typically including the expression, position, and message.

`getSimpleMessage()` returns only the error description, without the expression source.

`toDetailedString()` returns a fuller description, including the expression source and position when the exception stores them.

An example of the detailed form might look like:

    Expression [customer.address.city] @18: ...

The `@18` part is the position recorded by the exception. The message portion afterward describes the specific cause.

When displaying to developers, `toDetailedString()` is often helpful. When logging in production systems, consider whether the expression source contains sensitive data. `getSimpleMessage()` helps avoid automatically putting the full expression into logs, though `inserts` and `cause` must also be reviewed.

## 8. Catching Errors at the Right Phase

A clear way to organize code is to separate parsing and evaluation into two handling blocks:

    Expression expression;

    try {
        expression = parser.parseExpression(source);
    }
    catch (ParseException ex) {
        reportParseError(ex, source);
        return;
    }

    try {
        Object result = expression.getValue(context);
        useResult(result);
    }
    catch (EvaluationException ex) {
        reportEvaluationError(ex, source);
    }

You can handle SpEL-specific exceptions individually:

    private void reportParseError(
            ParseException ex,
            String originalSource) {

        String expressionSource =
            ex.getExpressionString() != null
                ? ex.getExpressionString()
                : originalSource;

        int position = ex.getPosition();

        if (ex instanceof SpelParseException spel) {
            SpelMessage code = spel.getMessageCode();
            Object[] inserts = spel.getInserts();

            logParseDiagnostic(
                code,
                inserts,
                expressionSource,
                position
            );
        }
        else {
            logGenericParseDiagnostic(
                expressionSource,
                position,
                ex.getSimpleMessage()
            );
        }
    }

For evaluation, use a similar approach and check for `SpelEvaluationException` before accessing the message code and inserts.

Keep the source that the application sent to the parser. This is especially useful when `getExpressionString()` returns `null` or the exception only attaches to part of a template.

## 9. Creating a Source Excerpt with an Error Position Marker

`getPosition()` only returns an offset. The application can extract a short snippet around that position and add a `^` marker so readers can locate it quickly.

Helper example:

    static String createErrorExcerpt(
            String source,
            int position) {

        if (source == null
                || position < 0
                || position > source.length()) {
            return "No valid source position";
        }

        int start = Math.max(0, position - 20);
        int end = Math.min(source.length(), position + 20);

        String excerpt = source.substring(start, end);

        StringBuilder marker = new StringBuilder();

        for (int i = start; i < position; i++) {
            marker.append(source.charAt(i) == '\t' ? '\t' : ' ');
        }

        marker.append('^');

        return excerpt
            + System.lineSeparator()
            + marker;
    }

Illustrative output example:

    customer.address.city
                      ^

This is a display snippet to aid debugging, not an official source range returned by SpEL. A position may only mark the start of a node or where the parser detected the error; it does not determine the entire token or the text span to replace.

When displaying the caret in a UI, account for tabs, Unicode combining characters, and supplementary characters. They can occupy a display width different from the count of UTF-16 code units.

## 10. Converting Offset to Line and Column

Expressions can be written across multiple lines. `getPosition()` is still an offset from the beginning of the source, not a line number.

Line and column can be computed by scanning the source from the start up to the offset:

    static int[] toLineAndColumn(
            String source,
            int position) {

        int line = 1;
        int column = 1;
        int limit = Math.min(position, source.length());

        for (int i = 0; i < limit; i++) {
            char ch = source.charAt(i);

            if (ch == '\n') {
                line++;
                column = 1;
            }
            else if (ch != '\r') {
                column++;
            }
        }

        return new int[] {line, column};
    }

Example:

    #customer.active and
    #customer.address.city

If the error position lies on the second line, the helper returns the line and column corresponding to the offset in the entire source.

This is the application's display convention. With tabs or multi-code-unit Unicode, the displayed column in an editor may differ from a count by Java `char`. If the marker needs to match the editor precisely, use the same offset and character width conventions that the editor uses.

Do not modify or normalize the source before computing positions. Removing whitespace, changing line endings, or replacing characters before parsing will cause offsets to no longer match the original source.

## 11. Error Position in Template Expressions

SpEL supports templates via `ParserContext`, such as the default `TemplateParserContext` recognizing `#{...}` blocks inside text.

Example:

    Expression template = parser.parseExpression(
        "Hello #{#customer.name}!",
        new TemplateParserContext()
    );

Two error groups must be distinguished:

- Template structure errors, such as a missing closing delimiter or mismatched brackets in the template. The template parser may report the position across the entire template string.
- Syntax errors inside a SpEL block. The template parser extracts the block content and passes that expression portion to the SpEL parser; the parsing exception may store the source and position relative to the inner expression portion.

The template parser also strips delimiters and trims the expression portion before parsing. Therefore, do not mechanically add the exception's position to the template source.

If highlighting on the original template is needed, retain metadata for each block: delimiter start position, prefix length, trimmed whitespace, and the actual parsed expression source. Only from that can a block offset be mapped back to an absolute offset in the template.

With multiple blocks, you need to know which block raised the exception. If this mapping is not preserved, display the source fragment provided by the exception instead of marking the wrong position on the whole template.

## 12. Position Is Not Always Available

Some exceptions created by custom integrations or code outside the parser may not attach a source string or an accurate position.

Before creating a snippet, check:

    String source = ex.getExpressionString();
    int position = ex.getPosition();

If `source` is `null`, use the original source kept by the application if you are certain it is the same expression being evaluated.

If `position` is less than `0` or exceeds `source.length()`, do not create a substring using that position.

If the exception is a general `EvaluationException`, do not assume it has `getMessageCode()` or `getInserts()`. These APIs only exist on SpEL-specific exceptions.

When position is unavailable, rely on the simple message, cause, sanitized stack trace, and rule ID information to continue investigating.

## 13. Cause and Errors from Invoked Methods

An expression can invoke a Java method:

    #customerService.calculateDiscount(#order)

If the method throws an exception, the error may be wrapped in the invocation exception. The SpEL position helps identify the method call node, while `cause` reveals the actual error inside the method.

Example:

    catch (EvaluationException ex) {
        Throwable cause = ex.getCause();

        if (cause != null) {
            log.error(
                "Evaluation failed: {}",
                ex.getSimpleMessage(),
                cause
            );
        }
    }

Do not look only at the position and conclude the parser is wrong. If the error occurred inside a method, check the cause, input parameters, and invoked Java logic.

Similarly, errors from `PropertyAccessor`, `MethodResolver`, `BeanResolver`, or `TypeConverter` can be wrapped in a SpEL exception. Error codes and `cause` help distinguish expression access errors from errors inside integration components.

## 14. Testing Error Position and Information

When writing tests for expressions, check the error code and position if position is an important part of the debugging experience.

Example:

    assertThatThrownBy(
        () -> parser.parseExpression("T(java.lang.Math).max(, 5)")
    )
    .isInstanceOf(SpelParseException.class)
    .satisfies(error -> {
        SpelParseException ex =
            (SpelParseException) error;

        assertThat(ex.getMessageCode())
            .isEqualTo(SpelMessage.RUN_OUT_OF_ARGUMENTS);

        assertThat(ex.getPosition())
            .isGreaterThanOrEqualTo(0);
    });

The test snippet illustrates checking the exception type, error code, and that the position has a valid value. When needing to assert an exact position, write the assertion according to the source and the Spring version the project uses.

Do not test by comparing the entire `getMessage()` if the message wording is not a stable application contract. Prefer exception type, `SpelMessage` code, needed `inserts`, and `position`.

For custom `PropertyAccessor` or `MethodResolver`, test cases where the resolver succeeds, rejects the target, and throws an error. The position in a custom exception may differ if the implementation does not supply an offset.

## 15. Logging Errors Without Exposing Data

Expressions can contain variable names, literal data, or user-provided values. Logging the entire source and detailed message may expose information that should not be stored.

A useful log typically includes:

- Rule ID or expression ID.
- Rule version.
- Parse or evaluation phase.
- Exception class and `SpelMessage` code if available.
- Position if valid.
- Sanitized simple message.
- Cause class or internal error code.
- Correlation ID for tracing.

Do not log the entire `EvaluationContext` or object graph just to find the error position. If you need to store the expression source for investigation, clearly define access permissions, retention periods, and sensitive-data redaction rules.

For user-provided expressions, avoid displaying the verbatim content to other users or sending it to broadly accessible logging systems.

## 16. Common Mistakes When Reading Position

| Misconception | Correct Understanding |
| --- | --- |
| getPosition() is always a line number | It is an offset in the expression string |
| Position always exists | Some exceptions do not store source or have an unknown position |
| Every error is SpelParseException | Template parsers and other integrations may throw a general ParseException |
| Every evaluation error is SpelEvaluationException | You may receive EvaluationException or another invocation exception |
| Position is the entire erroneous source region | The API only provides a single position, not a start/end range |
| getMessage() is just a short message | It typically includes source and position via toDetailedString() |
| getSimpleMessage() has the full source | It omits the expression string and position |
| Message text can be compared to classify errors | Use SpelMessage codes when the exception supports them |
| Template block position is always an absolute template offset | Expression blocks may be parsed as separate source fragments |
| Successful parse means evaluation will certainly succeed | Runtime errors only appear when getValue() runs |

## 17. Recommended Debugging Workflow

When an expression fails, proceed in order:

1. Determine whether the error occurred in `parseExpression` or `getValue`.
2. Catch `ParseException` or `EvaluationException` accordingly.
3. Retrieve the exception type, `getSimpleMessage()`, and `cause`.
4. If it is `SpelParseException` or `SpelEvaluationException`, read `getMessageCode()` and `getInserts()`.
5. Retrieve `getExpressionString()` and `getPosition()`; use the original source as a fallback when needed.
6. Validate that `position` is within bounds before extracting a snippet.
7. For multiline expressions, convert the offset to line/column using the application's display convention.
8. If using templates, determine whether the error belongs to the template structure or an expression block.
9. Check the root object, variables, property accessor, method resolver, or converter if the error occurred during evaluation.
10. Sanitize the source and inserts before logging or displaying.

This workflow separates syntax errors, runtime errors, and errors from integration components, helping find the root cause faster.

## 18. Key Points to Remember

- `parseExpression()` can throw `ParseException`; `getValue()` can throw `EvaluationException`.
- `SpelParseException` and `SpelEvaluationException` are SpEL-specific exceptions.
- `ExpressionException` provides `getExpressionString()`, `getPosition()`, `getSimpleMessage()`, and `toDetailedString()`.
- `getPosition()` is an offset in the expression string, not directly line/column.
- Position may be undefined; validate source and offset bounds before building a snippet.
- `SpelParseException` and `SpelEvaluationException` provide `getMessageCode()` and `getInserts()`.
- Use `SpelMessage` codes for classification instead of comparing message text verbatim.
- `getMessage()` typically includes source and position; `getSimpleMessage()` does not include source.
- `cause` helps find errors inside methods, accessors, resolvers, or converters.
- Templates can produce exceptions on the whole template or on an expression fragment inside a block.
- Position is only a point, not a complete source range.
- Do not log source, inserts, or context with sensitive data without redacting first.
- Test exception type, message code, and position against your project's Spring version.

When handling SpEL errors, separate parsing from evaluation, retrieve the position from the exception, and compare it against the exact parsed source. Use message codes, inserts, and cause to understand the error type; only create markers when the source and offset are valid. This makes error information helpful without pointing to the wrong position or leaking data inside the expression.

## References

- Spring Framework Reference — Evaluation and Exceptions: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — ExpressionException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionException.html
- Spring Framework Javadoc — ParseException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html
- Spring Framework Javadoc — SpelParseException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParseException.html
- Spring Framework Javadoc — SpelEvaluationException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelEvaluationException.html
- Spring Framework Source — ExpressionException: https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/ExpressionException.java
- Spring Framework Source — TemplateAwareExpressionParser: https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/common/TemplateAwareExpressionParser.java
