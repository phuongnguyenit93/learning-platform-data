# String Literals in SpEL: Single Quotes and Double Quotes

## 1. What is a String Literal?

In Spring Expression Language (SpEL), a string literal is a string value written directly inside an expression. When the parser encounters a string literal, it creates a value of type `java.lang.String` so the expression can return it, concatenate strings, compare, or call methods.

A simple example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'Hello, SpEL!'");
String message = expression.getValue(String.class);

System.out.println(message); // Hello, SpEL!
~~~

The string passed to `parseExpression` in the example above is `'Hello, SpEL!'`. The single quotes at both ends are SpEL syntax; the resulting value is only the content `Hello, SpEL!`, excluding the two quote characters.

SpEL allows both single quotes (`'`) and double quotes (`"`) to enclose a string literal. Both ways below represent a string:

~~~java
String fromSingleQuotes =
        parser.parseExpression("'Spring Framework'").getValue(String.class);

String fromDoubleQuotes =
        parser.parseExpression("\"Spring Framework\"").getValue(String.class);
~~~

Both variables receive the value `Spring Framework`. Choose a consistent quote style within an expression so readers can easily distinguish the start and end of a literal.

## 2. Distinguishing Java Quotes from SpEL Quotes

When calling the parser from Java, we are working with two layers of syntax:

1. Java uses double quotes to create a `String` object in Java source code.
2. SpEL reads the contents of that `String` object and uses single or double quotes to recognize the expression's string literal.

Example:

~~~java
String spelSource = "'Hello'";
Expression expression = parser.parseExpression(spelSource);
String value = expression.getValue(String.class);
~~~

In Java source code, `"'Hello'"` is a Java string. Its runtime value contains the characters `'Hello'`, and the SpEL parser understands that part as a string literal.

If you want SpEL to use double quotes, you must represent double quotes inside the Java string using Java escaping:

~~~java
String spelSource = "\"Hello\"";
Expression expression = parser.parseExpression(spelSource);
String value = expression.getValue(String.class);
~~~

Java processes `\"` before calling the parser. Therefore, the actual content that SpEL receives is `"Hello"`. The double quotes here belong to SpEL syntax, whereas the outermost pair of double quotes in the source code belongs to Java syntax.

Important rule: distinguish the Java string passed by the program from the SpEL expression string received by the parser. When encountering a parse error, print or debug the runtime value of the expression source variable to see which string the parser actually received.

## 3. When to Choose Single Quotes and When to Choose Double Quotes?

Both delimiter styles can create a string literal. The practical benefit of choosing one over the other usually lies in the string's content: using a delimiter different from the quotes that need to appear in the content reduces the need for escaping.

For example, content containing double quotes can be placed inside a single-quoted literal:

~~~java
String spelSource = "'She said \"Hello\"'";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // She said "Hello"
~~~

Conversely, content containing single quotes can be placed inside a double-quoted literal:

~~~java
String spelSource = "\"It's Spring\"";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // It's Spring
~~~

In the first example, single quotes mark the start/end of the SpEL literal; the double quotes inside are content. In the second example, double quotes mark the SpEL literal; the single quote in the word `It's` is normal content.

This choice is especially useful when an expression contains names, quotations, messages, or content with quote characters. If a string contains both kinds of quotes, choose the delimiter that appears less frequently in the content and escape any delimiter matching the enclosing delimiter according to SpEL syntax.

## 4. Escaping Quotes When Content Contains the Same Delimiter Type

If the content needs to contain the very quote character being used to enclose the literal, you need to escape that quote according to SpEL's rules. SpEL lets you repeat the corresponding delimiter to represent a quote character inside the string.

Example with a single-quoted literal:

~~~java
String spelSource = "'It''s Spring'";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // It's Spring
~~~

The two single quotes in the middle of the expression represent one single quote belonging to the content. The first and last quotes remain the opening/closing delimiters of the literal.

Similarly, with a double-quoted literal, you can repeat the double quote inside:

~~~java
String spelSource = "\"She said \"\"Hello\"\"\"";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // She said "Hello"
~~~

In this example, there are two processing steps: Java processes the escapes to build the expression source string; then SpEL receives a literal with double-quote delimiters and interprets the repeated double-quote pairs inside as a single double quote in the result.

When expressions are constructed dynamically, you should not arbitrarily concatenate strings to handle quotes. Explicitly control delimiters, escape content with the proper syntax, and prefer passing data via variables in the evaluation context if the data is not a fixed part of the expression.

## 5. Using String Literals in String Concatenation

The `+` operator can concatenate string literals together:

~~~java
Expression expression =
        parser.parseExpression("'Hello' + ' ' + 'Spring'");

String result = expression.getValue(String.class);
System.out.println(result); // Hello Spring
~~~

String literals can also be combined with variables in the evaluation context:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");

Expression expression =
        parser.parseExpression("'Hello, ' + #name + '!'");

String greeting = expression.getValue(context, String.class);
System.out.println(greeting); // Hello, Lan!
~~~

In this expression:

- `'Hello, '` is a string literal.
- `#name` is a variable named `name` in the evaluation context.
- `'!'` is a string literal containing an exclamation mark.
- The `+` operator joins the parts into one resulting string.

If data changes per request or per object, you should pass the data into the context as a variable instead of directly embedding that data into the expression source string. This allows reusing the expression and avoids errors caused by quotes or special characters in input data.

## 6. Using String Literals for Comparison

String literals frequently appear in comparison conditions:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("status", "PAID");

Expression expression =
        parser.parseExpression("#status == 'PAID'");

Boolean paid = expression.getValue(context, Boolean.class);
System.out.println(paid); // true
~~~

You can use double quotes for the same value:

~~~java
Expression expression =
        parser.parseExpression("#status == \"PAID\"");
~~~

The equality operator `==` evaluates two values. For strings, both content and value type matter; uppercase and lowercase letters differ, so `'PAID'` and `'paid'` are not the same content.

You can use literals in compound conditional expressions:

~~~java
Expression expression = parser.parseExpression(
        "#status == 'PAID' and #total > 0");
~~~

Quotes help the parser recognize `PAID` as a string literal. If you write `PAID` without quotes, SpEL will interpret it as a property name or identifier to be resolved in the context, not a character string.

## 7. Calling Methods on String Literals

A string literal is a `String` value, so an expression can invoke appropriate methods on it:

~~~java
Expression upperExpression =
        parser.parseExpression("'spring'.toUpperCase()");

String upper = upperExpression.getValue(String.class);
System.out.println(upper); // SPRING
~~~

Another example:

~~~java
Expression lengthExpression =
        parser.parseExpression("'Spring'.length()");

Integer length = lengthExpression.getValue(Integer.class);
System.out.println(length); // 6
~~~

You can call a method on a string variable:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("framework", "Spring");

Expression expression =
        parser.parseExpression("#framework.toUpperCase()");

String result = expression.getValue(context, String.class);
System.out.println(result); // SPRING
~~~

Quotes are only needed when representing string content directly. For variables, use the `#variableName` syntax; for properties of the root object, use the property name along the appropriate path.

## 8. Empty String and null Are Two Different Values

An empty string is a valid string literal, written as two adjacent quotes:

~~~java
String empty = parser.parseExpression("''").getValue(String.class);
System.out.println(empty.length()); // 0
~~~

The `null` value is written with the keyword `null` and represents a reference with no object:

~~~java
Object nullValue = parser.parseExpression("null").getValue();
~~~

Do not confuse `''` with `null`:

- `''` is a String object with length 0.
- `null` is not an empty String; it represents a value with no reference.
- Comparisons, method invocations, or type conversions may yield different results depending on these two cases.

If configuration may be missing or users may submit empty content, decide clearly how the application should handle empty strings, whitespace, or null.

## 9. String Literals Inside Template Expressions

In a template expression, `#{...}` marks the SpEL segment to be evaluated. Inside this pair of delimiters, string literals still follow the same single-quote or double-quote rules as regular SpEL expressions.

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
        "Message: #{'Hello, ' + #name + '!'}",
        templateContext);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");

String message = expression.getValue(context, String.class);
System.out.println(message); // Message: Hello, Lan!
~~~

Three kinds of delimiters must be distinguished in this example:

- Double quotes in Java code enclose the source string.
- `#{` and `}` delimit the expression part of the template.
- Single quotes inside `#{...}` enclose SpEL string literals.

If `TemplateParserContext` is not passed, the default parser will attempt to interpret the entire string `Message: ...` as a single SpEL expression. In that case, the fixed text outside is not automatically preserved as template content.

## 10. Common Mistakes When Writing Strings

**Forgetting SpEL delimiters**

~~~java
// PAID is interpreted as an identifier/property, not a string literal.
Expression expression = parser.parseExpression("status == PAID");
~~~

If you want to compare against a string, write a quoted literal:

~~~java
Expression expression = parser.parseExpression("status == 'PAID'");
~~~

**Confusing Java quotes with SpEL quotes**

~~~java
// This is a Java String containing the expression source: 'Hello'
String spelSource = "'Hello'";
~~~

The outermost double quotes belong to Java; the single quotes inside belong to SpEL. If you want the SpEL expression to use double quotes, you must escape them in Java source code.

**Escaping at the wrong layer**

A backslash may be processed by Java before SpEL sees the string. When debugging, inspect the runtime value of the expression source rather than only looking at how it is written in the Java file.

**Building expressions by concatenating user data**

If dynamic data contains quotes, manual string concatenation can alter the expression syntax or produce an unintended expression. Pass data using `EvaluationContext.setVariable(...)` and reference it with `#variableName`.

**Confusing an empty string with null**

`''` and `null` have different semantics. Explicitly check null conditions and string length if logic depends on empty data.

## 11. Comprehensive Example

The following example combines string literals, double quotes inside content, context variables, string concatenation, and method invocation:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");
context.setVariable("framework", "Spring");

Expression expression = parser.parseExpression(
        "'She said \"Hello\", ' + #name + ' is learning ' "
                + "+ #framework.toUpperCase()");

String message = expression.getValue(context, String.class);

System.out.println(message);
// She said "Hello", Lan is learning SPRING
~~~

Here the literals are enclosed by single quotes. The double quotes around the word `Hello` are string content; in Java source code, they are escaped so they exist in the Java string. Variables `#name` and `#framework` are retrieved from the context, and `toUpperCase()` is called on the value of the `framework` variable.

## 12. Key Takeaways

- SpEL supports string literals enclosed in either single quotes or double quotes.
- The outermost quotes are delimiters and do not appear in the returned string value.
- When calling the parser from Java, Java quotes and SpEL quotes belong to two different syntax layers.
- Use the opposite delimiter when content contains quotes; escape delimiters that match the enclosing delimiter according to SpEL rules.
- You can concatenate literals with `+`, compare literals, invoke methods on strings, and use literals inside template expressions.
- Use variables in `EvaluationContext` for dynamic data instead of manually concatenating data into the expression source.
- The empty string `''` is different from `null`.
