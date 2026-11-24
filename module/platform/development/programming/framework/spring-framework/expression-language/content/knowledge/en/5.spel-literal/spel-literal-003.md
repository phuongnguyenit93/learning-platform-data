# String Literals and Special Characters in SpEL

## Objective

A string literal is a text value written directly in a SpEL expression. It often appears when comparing properties, concatenating strings, passing arguments to methods, or creating display content. To read and write literals accurately, it is necessary to distinguish SpEL's quotes from the quotes of the language enclosing the expression (usually Java), and understand how SpEL handles quotes, whitespace, backslashes, and Unicode characters.

## 1. Basic Syntax

In modern SpEL, a string literal can be enclosed by single quotes (`'`) or double quotes (`"`). The part between the two delimiters is created as a `java.lang.String` value.

| SpEL Expression | Resulting Value |
| --- | --- |
| `'Hello World'` | `Hello World` |
| `"Hello World"` | `Hello World` |
| `'123'` | String `123`, not an integer. |
| `'true'` | String `true`, not a boolean. |
| `'null'` | String `null`, not the null value. |
| `'A'` | Single-character string `A`, not a Java `char`. |

Example of parsing and retrieving the result:

```java
ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression("'Hello World'")
        .getValue(String.class);

String numberText = parser.parseExpression("'123'")
        .getValue(String.class);
```

The result of `getValue(String.class)` is a `String`. If `123` is written without quotes, SpEL interprets it as a numeric literal; if `true` or `null` is written without quotes, they are a boolean literal and a null literal, respectively.

Documentation for older Spring versions may only illustrate single quotes. If the application must run on an older version, check the syntax supported by that version's parser; single quotes are the most widely compatible choice.

## 2. Including Quotes Inside String Content

The important rule is to double the same quote character being used as the literal delimiter. Do not use Java or C backslash rules to replace this rule.

| SpEL Expression | Result | Explanation |
| --- | --- | --- |
| `'Tony''s Pizza'` | `Tony's Pizza` | A single quote inside a single-quoted literal is written as two consecutive single quotes. |
| `"He said ""hello"""` | `He said "hello"` | A double quote inside a double-quoted literal is written as two consecutive double quotes. |
| `"It's ready"` | `It's ready` | A single quote is not the delimiter of a double-quoted literal, so it can be written directly. |
| `'He said "go"'` | `He said "go"` | A double quote is not the delimiter of a single-quoted literal, so it can be written directly. |

The most common example is a name or content containing a single quote:

```java
ExpressionParser parser = new SpelExpressionParser();

String spelSource = "'Tony''s Pizza'";
String name = parser.parseExpression(spelSource).getValue(String.class);
// name = "Tony's Pizza"
```

When needing to include both types of quotes, choose the less frequent one as the delimiter. For example, a string with many double quotes can be enclosed with single quotes: `'He said "go now"'`.

Do not write `\'Tony\\\'s Pizza\'` hoping that `\\\'` will escape quotes in the Java/C style. The correct way in SpEL is `'Tony''s Pizza'`.

## 3. Whitespace and Punctuation

Whitespace inside a string literal is data and is preserved, including leading/trailing whitespace, multiple consecutive spaces, and actual tab characters. Conversely, whitespace between tokens outside literals is usually only for formatting the expression and is ignored by the parser.

```spel
'  Spring   Expression Language  '
```

The value above preserves two leading spaces, three spaces between `Spring` and `Expression`, and two trailing spaces.

Characters such as dots, commas, colons, parentheses/brackets, plus signs, comparison signs, `#`, `@`, `{`, and `}` are all text content when they are inside a properly quote-closed literal:

```spel
'A + B = C; price >= 100; #name; {key:value}'
```

The expression above returns a string. Those characters are only treated as operators or SpEL syntax when they appear in a syntactic position outside a literal. For example, `1 + 2` performs addition, while `'1 + 2'` is just the text `1 + 2`.

## 4. Backslashes and Escape Sequences

Do not assume SpEL processes `\n`, `\t`, `\r`, or `\uXXXX` like Java. Inside a SpEL string literal, backslash is not a general escape mechanism; sequences like `\n` are kept as a backslash character and the letter `n`. The escape mechanism of Java source or JSON/XML/configuration may have already processed the string before SpEL receives it.

The example below creates a path with real backslashes. Java processes each `\\` pair into a single backslash character before passing the expression to SpEL:

```java
ExpressionParser parser = new SpelExpressionParser();
String pathExpression = "'C:\\temp\\file.txt'";
String path = parser.parseExpression(pathExpression).getValue(String.class);
// path = C:\temp\file.txt
```

If you need real newline or tab characters, create them in Java and pass them into the evaluation context as data:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("newline", System.lineSeparator());
context.setVariable("tab", "\t");

Expression expression = parser.parseExpression(
        "'Line 1' + #newline + 'Name:' + #tab + 'Lan'");
String result = expression.getValue(context, String.class);
```

`result` contains a newline between `Line 1` and `Name:`, followed by a tab before `Lan`. Passing via variables is also useful when the value is controlled by the operating system or application configuration.

## 5. Unicode and Vietnamese Characters

SpEL processes literal content as a Java `String`, so it can contain Vietnamese characters with diacritics, characters from other alphabets, currency symbols, and emojis:

```spel
'Xin chào, thế giới — Spring 🌱'
```

No extra SpEL escape characters are needed for ordinary Unicode characters. Ensure that source files, configuration files, requests, or storage systems use an appropriate encoding (usually UTF-8) so data is not corrupted into garbled characters before the parser receives it.

Technically, Java `String` stores strings in UTF-16. Therefore, when slicing strings or limiting length at the application layer, avoid splitting in the middle of a surrogate pair for characters outside the Basic Multilingual Plane, such as certain emojis.

## 6. Using String Literals in Larger Expressions

A string literal can be part of a comparison, string concatenation, method call, inline list, or inline map.

```java
ExpressionParser parser = new SpelExpressionParser();

// Compare a property with a literal
boolean isLan = parser.parseExpression("name == 'Lan'")
        .getValue(customer, Boolean.class);

// Concatenate literals and dynamic values
String message = parser.parseExpression("'Hello, ' + name + '!'")
        .getValue(customer, String.class);

// Call a method on a string literal
String upper = parser.parseExpression("'spring spel'.toUpperCase()")
        .getValue(String.class);
```

The results correspond to comparing the customer's name, generating a greeting based on the `name` property, and converting the string `spring spel` to uppercase. String literals can also serve as elements in an inline list or values of an inline map, for example `{'red', 'green'}` and `{'name': 'Lan'}`.

## 7. Distinguishing Java Quotes and SpEL Quotes

When writing SpEL in Java source, there are at least two syntax layers:

1. Java creates a `String` object from the string literal in source code.
2. SpEL parses that `String` content according to its own expression syntax.

Example:

```java
String spelSource = "'Tony''s Pizza'";
```

Java uses the outer double quotes to create `spelSource`. After Java compiles, the variable's value is the SpEL string `'Tony''s Pizza'`; then SpEL interprets the two consecutive single quotes as a single quote in the result.

When SpEL content is placed in annotations, XML, JSON, properties files, shell commands, or another DSL, the enclosing layer may have its own escape rules. Inspect the actual string passed to `parseExpression`, rather than inferring solely from how it is written in the outer layer.

## 8. Common Mistakes

| Symptom | Cause | How to Handle |
| --- | --- | --- |
| `ParseException` reports an unterminated string | Missing closing quote or inner quote was not doubled properly. | Check opening/closing delimiters and use `''` or `""` to represent the corresponding delimiter inside the literal. |
| Result still has backslash and letter `n` | SpEL keeps `\n` as two ordinary characters instead of converting to a newline. | Create a real newline character in Java and pass it through a context variable. |
| Java reports a compile error before SpEL runs | The outer Java string did not properly escape double quotes or backslashes. | Check the generated Java string and the SpEL string the parser receives separately. |
| `true`, `null`, or numbers are treated with the wrong type | The value was enclosed in quotes so it became a String. | Remove the quotes if the goal is a boolean, null, or numeric literal. |
| Whitespace is lost | Whitespace was placed outside the string literal or trimmed at the application layer before parsing. | Place the whitespace to keep inside quotes and check the data before the parser. |
| Data containing quotes breaks the expression | User data was concatenated directly into SpEL source. | Pass data into `EvaluationContext` using variables instead of concatenating expression strings. |

## 9. Passing Data Safely Instead of String Concatenation

Do not concatenate external input directly into SpEL source. A quote in the input can make the expression syntactically invalid; improperly concatenated data can also alter the expression structure.

Example of passing data via a variable:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("keyword", userInput);

Expression expression = parser.parseExpression("name == #keyword");
Boolean matched = expression.getValue(context, Boolean.class);
```

In this example, `userInput` is passed as a `String` value; quotes or operator characters inside the data do not become SpEL syntax. At the same time, only grant the context the objects and access capabilities that the expression actually needs.

## Key Takeaways

- Use single quotes or double quotes to create String literals depending on the Spring version in use; single quotes have broad compatibility.
- To include the delimiter itself inside a literal, double that delimiter: `'Tony''s'` or `"say ""hello"""`.
- The other type of quote can appear directly inside the literal.
- Whitespace, punctuation, and Unicode characters inside a literal are data and are preserved.
- Do not treat `\n` or `\t` as SpEL escape sequences; pass real control characters via variables if needed.
- Distinguish Java/JSON/XML escapes from SpEL syntax; the parser only receives the string after the outer layer has finished processing.
- For external data, use variables in `EvaluationContext` instead of concatenating data into expression source.

## References

- [Spring Framework Reference — Literal Expressions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/literal.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework source — SpEL Tokenizer](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/standard/Tokenizer.java)