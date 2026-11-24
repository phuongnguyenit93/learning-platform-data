# ParseException and Syntax Errors in SpEL

Spring Expression Language (SpEL) converts an expression string into an `Expression` object through an `ExpressionParser`. If the string does not follow SpEL's grammar, the parser cannot create an expression and throws a syntax parsing error. In Spring, the specialized error commonly encountered is `SpelParseException`, a form of `ParseException` that provides information about the position and error type detected by the parser.

It is necessary to distinguish parse errors from errors that occur during evaluation. A syntactically valid expression can still fail at runtime because a variable is not registered, a property does not exist, data types are incompatible, a bean cannot be resolved, or a method throws an exception. Distinguishing these two phases properly helps handle errors accurately and avoids mistakenly fixing syntax when the actual issue lies in the data or `EvaluationContext`.

## 1. Objectives and Prerequisites

After this lesson, you can:

- Explain what the parser does and when SpEL throws `ParseException`.
- Recognize `SpelParseException` and its diagnostic information.
- Distinguish syntax errors from evaluation errors and business logic errors.
- Identify common errors involving parentheses/brackets, quotes, operators, collections, and template delimiters.
- Use the error position to locate the syntax region that needs inspection.
- Write tests verifying valid expressions and invalid expressions.
- Parse an expression once and reuse it when appropriate.
- Return understandable configuration errors without exposing sensitive information.
- Control the source and size of expressions before bringing them into runtime.

You should know how to create a `SpelExpressionParser`, call `parseExpression()`, create an `EvaluationContext`, and evaluate an `Expression` using `getValue()`.

## 2. At Which Phase Does ParseException Occur?

Working with SpEL typically has two phases:

1. Parse source string: the parser reads the syntax, checks the grammar, and creates an `Expression` object.
2. Evaluate expression: the expression uses the root object, variables, property accessors, resolvers, and runtime data to compute the result.

Example of valid syntax:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#quantity * #unitPrice");
~~~

At parse time, the parser can create the expression even if the context does not yet have the `quantity` or `unitPrice` variables. Missing variables are only detected during evaluation.

Conversely, an expression missing an operand:

~~~text
#quantity *
~~~

cannot be parsed into a complete expression and causes a parse error immediately at `parseExpression()`.

Basic flow:

~~~text
Source string
     |
     v
ExpressionParser.parseExpression(...)
     |
     +---- invalid syntax ----> ParseException
     |
     v
Expression
     |
     v
Expression.getValue(context)
     |
     +---- data/permission/runtime error -> EvaluationException
     |
     v
Result
~~~

`ParseException` indicates that the parser could not understand the source according to the grammar. It is not a general notification for all SpEL errors.

## 3. What Is SpelParseException?

Spring provides `SpelParseException` in the `org.springframework.expression.spel` package. This is a specialized exception for SpEL parsing errors and extends `ParseException` from the Spring Expression API.

Useful information may include:

- The position where the parser detected the error.
- A message code describing the error type.
- Values inserted into the error message, such as the related token or symbol.
- A message explaining the error.

Example of catching the error:

~~~java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.SpelParseException;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

try {
    parser.parseExpression("#quantity *");
}
catch (SpelParseException ex) {
    int position = ex.getPosition();
    String message = ex.getMessage();

    // Record the configuration error according to the application's policy.
}
~~~

An application can catch `ParseException` at a general abstraction level if SpEL-specific information is not needed. If the message code or specialized information is needed, catch `SpelParseException`.

You should not rely on the full message content to determine business logic. The displayed message may change depending on the Spring version or message formatting. Use the exception type and structured information for handling; use the message primarily to assist with diagnostics.

## 4. Reading the Error Position

`SpelParseException` provides the position where the parser detected the error via `getPosition()`. This position helps narrow down the region to inspect in the source expression.

Example:

~~~text
#order.total + )
~~~

The parser may detect a closing parenthesis with no matching preceding expression. Inspect the source around the reported position, check the tokens immediately before and after it, and compare with the expected expression structure.

When displaying errors in an editor:

- Keep the parsed source string intact.
- Use the exception position to highlight near the problematic character.
- Do not assume the position is always a line number or column number.
- If the template is multiline, build your own offset-to-line/column mapping from the original source.
- Check how the API and Spring version represent the position before converting it into a display index for users.

For sources containing Unicode characters outside the BMP, Java character indices may relate to UTF-16 code units. If the editor uses code points or grapheme clusters, convert the offset before highlighting accurately.

The position where the parser detects an error is not always where the author originally made the mistake. For example, a missing opening quote may cause the parser to only recognize an error at a token appearing later. Check the entire surrounding region rather than fixing only the single highlighted character.

## 5. Common Syntax Errors

### 5.1. Missing or Extra Brackets/Parentheses

Example of a missing closing parenthesis:

~~~text
(#price + #tax
~~~

Example of an unmatched closing parenthesis:

~~~text
#price + #tax)
~~~

How to handle:

- Count pairs of parentheses, square brackets, and curly braces according to the expression structure.
- Check nested expressions and inline maps/lists.
- Break long expressions into smaller parts to find the unbalanced position.
- Do not add brackets arbitrarily before determining the intended structure.

### 5.2. Unclosed String Literal

Example:

~~~text
#user.name == 'An
~~~

The string starts with a single quote but has no closing quote. Check opening/closing quotes and string escaping rules in SpEL.

If the source is built from a Java string, JSON, or XML, also check the escaping layer of the language containing the expression. A backslash may be processed at the Java layer before SpEL receives the string.

### 5.3. Missing Operand or Operator

Example:

~~~text
#quantity *
~~~

~~~text
#amount > and #active
~~~

Verify that each operator has enough operands and uses valid SpEL keywords/operators. If concatenating expression fragments in code, confirm that individual fragments do not leave a dangling operator at the boundary.

### 5.4. Incorrect Variable Syntax

Variables in SpEL have the `#` prefix:

~~~text
#customerName
~~~

Writing `customerName` without `#` is usually interpreted as a property on the root object, not a variable. This may be an evaluation error if the grammar is valid but the root object lacks that property; it is not necessarily a `ParseException`.

Distinguish syntax errors from name resolution errors. The syntax `#customerName` can parse successfully even when the context has not registered the variable.

### 5.5. Incorrect Collection or Map Access Syntax

Map indexing example:

~~~text
#settings['theme']
~~~

Selection example:

~~~text
#orders.?[total > 100]
~~~

Projection example:

~~~text
#orders.![number]
~~~

Dots, square brackets, and delimiters must be in the right positions. When an expression combines multiple collection operations, check each segment individually and then combine them.

### 5.6. Incorrect Method Call Syntax

Valid example:

~~~text
#calculator.calculate(#amount)
~~~

Common errors include missing method call parentheses, extra commas between arguments, or unclosed string literals. A non-existent method or incompatible signature is usually detected during the resolution/evaluation phase, even though the method call syntax remains valid.

## 6. Errors in Template Expressions

A template expression combines literal text with SpEL segments inside delimiters. By default, `TemplateParserContext` uses `#{` and `}` as prefix and suffix.

Example:

~~~java
Expression template = parser.parseExpression(
    "Hello, #{#name}!",
    new TemplateParserContext()
);
~~~

Common errors:

- Missing closing `}`.
- Invalid expression inside the delimiter.
- Using the delimiter of another template engine by mistake.
- Literal string contains delimiters but is not handled according to template rules.
- Using a `TemplateParserContext` that does not match the source format.

Example of a missing closing delimiter:

~~~text
Hello, #{#name!
~~~

Check the template source and the parser context passed to `parseExpression()`. A string might parse as a regular expression but fail as a template, or vice versa, because the parser context changes how the source is interpreted.

If custom delimiters are used, store the delimiter configuration together with the template version. When reopening the template, you must use the same `ParserContext` to parse it.

## 7. Distinguishing ParseException from Evaluation Errors

This is the most important distinction when diagnosing.

| Symptom | Typical Phase | Typical Error Type |
|---|---|---|
| Missing operand, bracket, or quote | Parse | SpelParseException |
| Token not in grammar | Parse | SpelParseException |
| Unregistered variable | Evaluate | SpelEvaluationException or appropriate EvaluationException |
| Non-existent property | Evaluate | Property/accessor error |
| Method not found | Evaluate | Method resolution error |
| Type in T(...) cannot be resolved | Evaluate | Type resolution error |
| Bean reference does not exist | Evaluate | Bean resolution error |
| Argument cannot be converted | Evaluate | Conversion error |
| Method throws an exception | Evaluate | Execution error wrapped in a Spring exception |
| Condition returns false | Business logic | Not a parse error |

Example:

~~~text
#unknownVariable
~~~

This syntax is valid. If the context does not register the variable, the error occurs during evaluation.

Similarly:

~~~text
#customer.nonExistingProperty
~~~

The syntactic structure may be valid, but the property is not found when the expression runs on the actual object.

Do not alter the grammar when the error lies in data, context, or the model. Determine whether the exception originates from `parseExpression()` or `getValue()` before handling it.

## 8. Structuring Code to Separate Parse and Evaluate

Place the two phases in separate handling blocks to categorize errors clearly:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (SpelParseException ex) {
    throw new IllegalArgumentException(
        "Expression syntax is invalid", ex);
}

try {
    return expression.getValue(context);
}
catch (EvaluationException ex) {
    throw new IllegalStateException(
        "Expression could not be evaluated", ex);
}
~~~

This is an example handling structure. Real-world applications should use appropriate domain exceptions and avoid returning raw internal messages to end users.

Separating parse and evaluate has the following benefits:

- Know which phase produced the error.
- Ability to validate expressions before publishing.
- Ability to cache parsed `Expression` objects by source/version.
- Each evaluation can use a separate context with runtime data.
- Logs and metrics can classify syntax errors and runtime errors separately.

If parsing is performed at startup or when saving a policy, syntax errors can be detected early before business requests use the expression.

## 9. Parse Once and Reuse Expression

If the expression source does not change, there is no need to re-parse on every evaluation.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#subtotal * (1 + #taxRate)");
~~~

Then evaluate with different contexts:

~~~java
StandardEvaluationContext contextA =
    new StandardEvaluationContext();
contextA.setVariable("subtotal", new BigDecimal("100"));
contextA.setVariable("taxRate", new BigDecimal("0.10"));

StandardEvaluationContext contextB =
    new StandardEvaluationContext();
contextB.setVariable("subtotal", new BigDecimal("250"));
contextB.setVariable("taxRate", new BigDecimal("0.08"));

Object resultA = expression.getValue(contextA);
Object resultB = expression.getValue(contextB);
~~~

`Expression` holds the parsed structure; runtime data comes from the passed context.

If expressions are configured by administrators, parse and validate syntax upon saving or publishing. Cache by ID and version so that when content changes, the application does not accidentally use an old `Expression`.

Do not share a mutable `EvaluationContext` across requests just because the `Expression` is reused. `Expression` and context have different lifecycles and responsibilities.

## 10. Validating Source Before Parsing

If expressions are entered via an admin interface, input checks can be performed before calling the parser:

- Limit the source length.
- Check that the source is non-empty if the use case requires it.
- Determine the correct parser context/delimiter.
- Associate the source with a policy ID and version.
- Identify the author and edit permissions.
- Do not concatenate request data directly into the source.
- Do not use simple regex to conclude an expression is safe.
- Parse using the parser with the exact runtime version and configuration.

Regex can be useful for preliminary format checks, but it does not replace a parser. SpEL grammar includes nested expressions, string literals, collections, and many operators; a regex banning characters can miss syntax or falsely reject valid expressions.

A successful parse only confirms syntax. It does not prove the expression is safe, has proper access permissions, or returns the right business result.

## 11. Error Messages for Users and Logs for Developers

Do not display raw stack traces or internal class details to end users.

Information can be separated as follows:

**Messages for configurators:**

- The expression is invalid.
- Approximate position where the parser detected the error.
- Suggestions to check parentheses/brackets, quotes, or operators.
- Reference error code for lookup.

**Internal log information:**

- Policy ID and version.
- Parser context or template type.
- Exception class and message code.
- Position if available.
- Correlation ID of the request/publish process.
- Redacted source if it contains sensitive data.

An expression source may contain field names, business structures, or improperly embedded secrets. Only log the full source when data policy permits and access/retention controls are in place.

Do not use message text as a stable error code for clients. Map exceptions to application-managed error codes.

## 12. Testing ParseException

Unit tests should verify that valid expressions parse successfully and syntactically invalid expressions are rejected.

JUnit example:

~~~java
class SpelSyntaxTest {

    private final ExpressionParser parser =
        new SpelExpressionParser();

    @Test
    void parsesValidExpression() {
        assertThatCode(() ->
            parser.parseExpression("#amount > 100")
        ).doesNotThrowAnyException();
    }

    @Test
    void rejectsMissingOperand() {
        assertThatThrownBy(() ->
            parser.parseExpression("#amount >")
        ).isInstanceOf(SpelParseException.class);
    }
}
~~~

You can also check `position` or `message code` if tests need to ensure the editor UI displays diagnostic information. Avoid asserting the full message because formatting may change across versions.

A test suite should cover:

| Case | Expected Result |
|---|---|
| Valid arithmetic expression | Parses successfully |
| Expression missing operand | ParseException |
| Unclosed string literal | ParseException |
| Unbalanced brackets/parentheses | ParseException |
| Template missing closing delimiter | ParseException |
| Template with valid custom delimiter | Parses successfully |
| Unregistered variable | Parses successfully, fails evaluation depending on context |
| Non-existent property | Parses successfully, evaluation fails |
| Unresolved method | Parses successfully, evaluation fails |
| Type conversion failure | Parses successfully, evaluation fails |
| Expression returns false | Parses/evaluates successfully, business result is false |

This test suite ensures grammar errors are not confused with runtime errors.

## 13. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Fix |
|---|---|---|
| ParseException at end of expression | Missing operand or closing token | Check the last operator and the preceding source |
| Error near brackets/parentheses | Missing/extra or improperly nested brackets | Match bracket pairs segment by segment |
| Error near quotes | Unclosed string literal or improper escaping | Check strings at Java/XML/JSON layers as well |
| Template fails to parse | Missing prefix/suffix or wrong ParserContext | Check TemplateParserContext and delimiters |
| Parser reports error at a seemingly valid position | The real error may be at an earlier token | Inspect the surrounding region and expression structure |
| Parse succeeds but getValue fails | Confusing runtime errors with syntax errors | Check EvaluationException and context |
| Variable not found | Variable not set via setVariable or wrong context used | Register the exact name and pass the right context |
| Property not found | Model/accessor does not provide the property | Check getters, fields, and PropertyAccessor |
| Message differs after upgrading Spring | Message format or parser diagnostics changed | Rely on exception type, code, and position; update tests accordingly |
| Error only occurs in production | Parser context, version, or source differs from test environment | Record parser configuration and policy version |

## 14. Practice Exercises

1. Parse a valid arithmetic expression and read the result.
2. Try an expression missing an operand and catch `SpelParseException`.
3. Create a string literal missing a closing quote and observe the position reported by the parser.
4. Try missing/extra parentheses in a nested expression.
5. Create a template with default prefix/suffix and intentionally omit the closing delimiter.
6. Create a `TemplateParserContext` with custom delimiters and test both valid and invalid sources.
7. Parse a valid variable expression without registering the variable; compare parse errors with evaluation errors.
8. Use a non-existent property to observe the error in the evaluation phase.
9. Write a JUnit test checking the exception type and position.
10. Create a small editor that displays the error near the position detected by the parser without exposing stack traces.
11. Parse expressions when publishing a policy and store the policy version.
12. Test the same source on the Spring version deployed by the application to confirm actual diagnostics.

## 15. Checklist for Handling ParseException

- [ ] Did the error originate from `parseExpression()` or `getValue()`?
- [ ] Is the exception a `SpelParseException`?
- [ ] Are the expression source version and parser context correct?
- [ ] Are parentheses, square brackets, and curly braces balanced?
- [ ] Are string literals closed and properly escaped?
- [ ] Does every operator have enough operands?
- [ ] Is the syntax for variables, indexing, selection, and projection correct?
- [ ] Do the template prefix/suffix match the `ParserContext`?
- [ ] Have you checked the source around the reported `position`?
- [ ] Have you distinguished missing variable/property/method names from syntax errors?
- [ ] Are expression length and source restricted?
- [ ] Are there tests for valid expressions, parse errors, and evaluation errors?
- [ ] Do user-facing error messages avoid exposing stack traces and sensitive data?

## 16. Conclusion

`ParseException` occurs when `ExpressionParser` cannot convert a source into a valid `Expression` structure. `SpelParseException` provides specialized information such as position and message code to aid diagnostics. An expression that parses successfully can still fail during evaluation due to variables, properties, methods, types, beans, or conversion. Separate parsing from evaluation, inspect the source around the error position, write tests for both phases, and handle messages using application error codes. Parsing early when publishing configuration helps detect syntax errors before policies reach runtime.