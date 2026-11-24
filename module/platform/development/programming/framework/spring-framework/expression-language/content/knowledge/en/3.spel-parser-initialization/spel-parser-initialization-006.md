# Parse Errors and Error Position in Expressions

When working with Spring Expression Language (SpEL), the parser turns an expression string into an **Expression** object so the application can evaluate it later. If the string does not conform to SpEL syntax, an error occurs immediately during the parse step. Reading the exception type and error position accurately helps identify which token is invalid, which syntax element is missing, and how to fix the expression.

One distinction to maintain throughout this lesson: **parsing fails on syntax errors; evaluation executes the expression within a context**. An expression can parse successfully yet still fail during evaluation because a property does not exist, a method cannot be called, a value is null, or a type conversion fails.

## 1. At which stage does parsing happen?

A typical processing flow consists of three steps:

1. Create an **ExpressionParser**.
2. Call **parseExpression(...)** to parse the string and obtain an **Expression**.
3. Call **getValue(...)** when evaluating the expression with a root object or **EvaluationContext**.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("order.total > 100");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Boolean result = expression.getValue(context, Boolean.class);
~~~

If the expression has invalid syntax, the error is thrown at the **parseExpression** call. For example:

~~~java
parser.parseExpression("order.total >");
~~~

The expression above ends with a comparison operator but is missing the right-hand operand. The parser cannot construct a valid expression and throws a parse error.

Conversely, the following expression can parse successfully:

~~~java
Expression expression =
        parser.parseExpression("order.unknownProperty > 100");
~~~

The parser can build the expression tree without needing to know whether **order** has an **unknownProperty** property. Only when calling **getValue** does SpEL access the root object and potentially raise an evaluation error if that property does not exist.

Therefore, when investigating an error, determine whether the exception occurred in **parseExpression** or **getValue**. Do not lump both stages into one generic message such as “invalid expression”.

## 2. Exception types when parsing SpEL

### 2.1. ParseException

**org.springframework.expression.ParseException** is the base exception for expression parsing errors. It extends **EvaluationException** and provides information about the expression string along with the position where the error occurred.

Useful details include:

- **getExpressionString()**: the expression string associated with the error.
- **getPosition()**: the position where the parser reported the error.
- **getMessage()**: the message explaining the error.

You can catch **ParseException** if handling code only needs one general exception type for the parse step.

### 2.2. SpelParseException

**org.springframework.expression.spel.SpelParseException** is the specific exception type of the SpEL parser. In addition to the basic information from **ParseException**, it provides diagnostic details via SpEL's message code:

- **getMessageCode()**: the **SpelMessage** code describing the error category.
- **getInserts()**: additional values used to construct the error message.
- **getPosition()**: the position where the parser detected the issue.

For example, the parser may report an unexpected token, a missing closing delimiter, or trailing data after an otherwise valid expression. The message code helps distinguish these cases without having to parse the English text in **getMessage()**.

The full message usually contains the expression, position, and error code. Exact wording may vary across Spring versions and error contexts. When writing program logic, use the structured properties of the exception rather than splitting the **getMessage()** string to infer the position or error type.

### 2.3. Catching parse errors and retrieving diagnostic information

~~~java
import java.util.Arrays;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.ParseException;
import org.springframework.expression.spel.SpelParseException;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class SpelParseDiagnostic {

    public static void main(String[] args) {
        String source = "order.total >";

        ExpressionParser parser = new SpelExpressionParser();

        try {
            Expression expression = parser.parseExpression(source);
            System.out.println("Parsed: " + expression.getExpressionString());
        } catch (ParseException ex) {
            System.out.println("Expression: " + ex.getExpressionString());
            System.out.println("Position: " + ex.getPosition());
            System.out.println("Message: " + ex.getMessage());

            if (ex instanceof SpelParseException spelEx) {
                System.out.println("Message code: "
                        + spelEx.getMessageCode());
                System.out.println("Inserts: "
                        + Arrays.toString(spelEx.getInserts()));
            }
        }
    }
}
~~~

In the example, **ParseException** handles the general case. When the actual exception is a **SpelParseException**, the program can extract the error code and diagnostic arguments as well.

There is no need to catch and construct a new **SpelParseException** just to change the message. Preserve the original exception as the **cause** if you need to wrap it in an application-layer exception.

## 3. Understanding the error position

**getPosition()** returns an offset in the expression string that the parser was parsing. This position is for syntax diagnostics, not necessarily the location of the original mistake made by the expression author.

Example:

~~~java
String source = "price + * quantity";
~~~

The parser may detect that the **\*** token is invalid at a position expecting an operand. However, what the author meant to write might have been without the extra **+** sign or with a missing value in between. Read the entire expression and message, not just the single character at the offset.

### 3.1. Offset and character index

In Java, strings are indexed by UTF-16 code units. Therefore, the exception's offset should be used directly against the exact Java string passed into the parser:

~~~java
int position = ex.getPosition();

if (position >= 0 && position <= source.length()) {
    char characterAtPosition =
            position < source.length()
                    ? source.charAt(position)
                    : '\0';
}
~~~

A few notes:

- The offset is normally understood as a 0-based index into the input string.
- The value can be at the end of the string when the parser expects a token and no characters remain.
- If the position is negative or out of bounds of the string, do not build a caret by calling **substring** directly.
- Unicode characters outside the Basic Multilingual Plane occupy two UTF-16 code units. Consequently, the Java offset does not always equal the number of Unicode code points the user visually sees.
- Tabs, combining characters, and display fonts can shift the caret column in a UI away from the visual position.

The safe approach is to keep the original input string intact and apply **getPosition()** on that exact string. Do not trim, normalize whitespace, or strip characters before matching the offset. If the application transforms the expression before parsing, store a mapping from the transformed string back to the original string.

### 3.2. Position reported by the parser vs. position to fix

The parser normally reports where it can no longer proceed according to the current grammar. This position is useful for narrowing down the area, but it is not guaranteed to be the only character that needs fixing.

Example:

~~~text
price + * quantity
        ^
~~~

The **\*** symbol is the token the parser encountered while expecting an operand. How to fix it depends on intent:

~~~text
price * quantity
~~~

or:

~~~text
price + discount * quantity
~~~

Do not automatically delete the token at **position** and re-parse. Doing so may turn the expression into a different valid syntax with the wrong business meaning.

## 4. Displaying a caret at the error position

An intuitive way to present diagnostics is displaying the line containing the error and a **^** marker beneath the offset. For single-line expressions, a simple helper can be used:

~~~java
static String formatCaret(String source, int position) {
    if (position < 0 || position > source.length()) {
        return source;
    }

    int lineStart = source.lastIndexOf('\n', position - 1) + 1;
    int lineEnd = source.indexOf('\n', position);

    if (lineEnd < 0) {
        lineEnd = source.length();
    }

    String line = source.substring(lineStart, lineEnd);
    if (line.endsWith("\r")) {
        line = line.substring(0, line.length() - 1);
    }

    int column = Math.min(position - lineStart, line.length());

    return line + System.lineSeparator()
            + " ".repeat(column) + "^";
}
~~~

Usage:

~~~java
String source = "price + * quantity";

try {
    parser.parseExpression(source);
} catch (ParseException ex) {
    System.out.println(ex.getMessage());
    System.out.println(formatCaret(source, ex.getPosition()));
}
~~~

Illustrative output:

~~~text
price + * quantity
        ^
~~~

This helper is suited for logs or simple examples. For multi-line expressions, the UI should also display line and column numbers. For tabs, calculate the display position after expanding tabs according to the editor's rules. For Unicode, convert the UTF-16 offset to an appropriate display index if the UI counts by code points or grapheme clusters.

If the expression contains sensitive user-entered data, consider masking or truncating the content before logging. You can store the error code, offset, and a sanitized context snippet instead of logging the entire string.

## 5. Common causes of parse errors

| Error category | Invalid example | What to check |
|---|---|---|
| Missing operand | **price +** | Check the operator at the end of the expression and the part right after it |
| Misplaced operator | **price + * quantity** | Check the order of operators and operands |
| Missing closing parenthesis | **(price + tax** | Match pairs of parentheses |
| Missing closing bracket | **items[0** | Check element access expressions |
| Unclosed string | **'Spring** | Check single or double quotes |
| Method call missing closing parenthesis | **customer.getName(** | Check the argument list and parentheses |
| Extra or missing comma | **max(10,,20)** | Check argument separators |
| Trailing token at the end | **price 123** | Check if any characters remain after a valid expression |
| Invalid property access syntax | **customer.first-name** | If the property name contains a hyphen, consider accessing it via appropriate index/key syntax |
| Wrong template delimiter | **Hello #{name** | Check the prefix/suffix of ParserContext |

Some strings look like Java or SQL syntax but do not mean the same thing in SpEL. When a property name contains a hyphen, the expression:

~~~java
customer.first-name
~~~

may be interpreted by the parser as property access combined with subtraction, rather than a single property name. If the property is a key in a map, it can be written as:

~~~java
customer['first-name']
~~~

Access syntax must match the actual object type and the accessor configured in the evaluation context.

## 6. Parsing regular expressions vs. template expressions

**ExpressionParser** has an overload accepting **ParserContext**. This parameter tells the parser whether the input string is a regular expression or a template containing expression segments.

Regular expression:

~~~java
Expression expression =
        parser.parseExpression("user.name.toUpperCase()");
~~~

A template expression can contain static text and SpEL parts marked by delimiters:

~~~java
import org.springframework.expression.common.TemplateParserContext;

Expression template = parser.parseExpression(
        "Hello #{user.name}",
        new TemplateParserContext()
);
~~~

**TemplateParserContext** defaults to **#{** as the prefix and **}** as the suffix. If the application defines custom delimiters, the same **ParserContext** must be used when parsing to avoid misdiagnosing missing or extra delimiters.

When debugging templates:

1. Keep the entire template string passed in unchanged.
2. Identify which **ParserContext** the parser is using.
3. Check the prefix/suffix pair and the expression part between them.
4. Read **getPosition()** along with the exception message to see which region the parser flagged.
5. If displaying the error to users, map the offset back to the corresponding template segment before highlighting it in the editor.

Do not manually strip static text and parse the **#{...}** part with a plain parser if the goal is to reproduce the exact error from the original run. Changing the input or **ParserContext** can change the resulting offset and error.

## 7. Distinguishing ParseException from evaluation errors

The two stages have different exceptions and need to be handled separately:

| Stage | Common exception | Example |
|---|---|---|
| Parse | **ParseException**, more specifically **SpelParseException** | **price +** |
| Evaluate | **EvaluationException**, more specifically **SpelEvaluationException** | Reading a nonexistent property or calling an invalid method |
| Type conversion during evaluation | May throw **EvaluationException** | Unable to convert value to parameter type |

Example separating the two stages:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("customer.age > 18");
} catch (ParseException ex) {
    // Invalid syntax: handle position and parse information.
    throw new IllegalArgumentException(
            "Invalid SpEL syntax at position " + ex.getPosition(),
            ex
    );
}

try {
    Boolean result = expression.getValue(context, Boolean.class);
    System.out.println(result);
} catch (EvaluationException ex) {
    // Syntax parsed successfully, but evaluation in context failed.
    throw new IllegalStateException(
            "Cannot evaluate the configured expression",
            ex
    );
}
~~~

The example above intentionally separates two **try/catch** blocks. In production code, you can use distinct business exceptions for each stage, while preserving the original exception as the **cause** so stack traces and diagnostic information are not lost.

An expression that parses successfully does not prove that:

- The root object has all referenced properties.
- Called methods exist or are accessible.
- Runtime values have compatible types.
- ConversionService has the required converter.
- Operations can be executed with the actual values.

Those conditions are only fully checked when evaluating the expression in a concrete context.

## 8. Workflow for investigating a parse error

When you receive a **SpelParseException**, you can follow this sequence:

1. **Preserve the original input.** Record the exact string and **ParserContext** passed into the parser. Do not trim or edit the string before reproducing.
2. **Confirm the right stage.** Check whether the exception occurred directly inside **parseExpression** or after calling **getValue**.
3. **Read the offset and error code.** Retrieve **getPosition()**, **getMessageCode()**, and **getInserts()** when the exception is a **SpelParseException**.
4. **Isolate the syntax.** Display the error line with a caret; inspect operators, parentheses, quotes, and delimiters.
5. **Create a minimal expression.** Simplify the expression in a test environment to pinpoint the failing token or construct.
6. **Write regression tests.** Keep one invalid case to confirm the parser reports an error and one valid case to confirm the corrected syntax.
7. **Check the evaluate stage separately.** After parsing succeeds, evaluate against representative root objects and contexts to catch runtime errors.

Do not rely solely on the text of **getMessage()** for programmatic logic. Human-readable messages may change across versions and locales. Use the exception type, offset, and message code for structured diagnostics; only display friendly messages at the UI layer.

## 9. Designing error messages for applications

If the application lets users enter expressions, normalize parse error results into an application diagnostic structure:

~~~java
public record ExpressionDiagnostic(
        String code,
        int position,
        String message
) {
}
~~~

Example of converting an exception to a diagnostic:

~~~java
static ExpressionDiagnostic toDiagnostic(ParseException ex) {
    String code = "SPEL_PARSE_ERROR";

    if (ex instanceof SpelParseException spelEx) {
        code = spelEx.getMessageCode().name();
    }

    return new ExpressionDiagnostic(
            code,
            ex.getPosition(),
            "Expression has invalid syntax"
    );
}
~~~

This structure keeps APIs or UIs from depending directly on Spring's full exception strings. You can send **position** back to the editor to highlight the error region, while translating the display message into the application's language.

When designing diagnostics, keep in mind:

- **position** must correspond to the exact version of the string that the parser received.
- Do not include sensitive expression contents in responses or public logs.
- Do not treat **code** as a free-form string to parse; obtain the code from the specific exception.
- Keep the original exception in controlled internal logs if deep investigation is needed.
- If the application modifies or normalizes expressions itself, map positions between the input string and the string received by the parser.

## 10. Safety boundaries when handling user-supplied expressions

A parse error message only says that the string does not follow the grammar. It does not prove that a valid expression is safe to run.

If the application accepts SpEL from users, design **EvaluationContext** with appropriate privileges, restricting which properties, methods, types, or access capabilities the expression is permitted to use. Do not evaluate untrusted expressions in a context with full application privileges just because the parse step succeeded.

Some principles:

- Allow only the expression features that the business case requires.
- Restrict type references, constructors, methods, and bean access when not needed.
- Consider **SimpleEvaluationContext** if only a limited subset of SpEL features is required.
- Do not use catching **SpelParseException** as a security control mechanism.
- Limit input size and handle errors in a controlled manner to prevent oversized expressions from consuming excessive resources.
- Do not automatically re-execute an expression modified based on parser guesswork.

## 11. Summary

Parse errors occur when the parser cannot analyze a string according to SpEL syntax. **ParseException** provides general information about the expression and position; **SpelParseException** adds SpEL-specific error codes and diagnostic arguments.

When handling errors, preserve the original input string, read **getPosition()** and the message code, display a caret if appropriate, and then re-check the grammar. Always distinguish parsing from evaluation: successful parsing only confirms that the syntax structure can be turned into an **Expression**, whereas property access, method invocation, and computation are only verified when evaluating inside an actual **EvaluationContext**.
