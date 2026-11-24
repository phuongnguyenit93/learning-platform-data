# The matches Operator with Regular Expressions

## Objectives

The **matches** operator in Spring Expression Language (SpEL) tests whether a string matches a regular expression. The result is a Boolean, so this operator is commonly used to validate formats, classify codes, check input rules, or combine with other business conditions.

After this lesson, you will be able to:

- Write matches syntax with strings and regular expressions.
- Understand how SpEL uses Java regular expressions and full-string matching rules.
- Choose appropriate character classes, quantifiers, groups, and alternation.
- Combine matches with variables, properties, null conditions, and logical operators.
- Avoid errors caused by data types, escaping, and overly complex patterns.
- Test valid cases, invalid cases, and boundary values.

## 1. Basic Syntax

Syntax of the operator:

~~~text
stringExpression matches 'regular-expression'
~~~

The left side must evaluate to the string to be checked. The right side is a string containing the regular expression. The operator returns a Boolean:

- **true** if the entire input string matches the pattern.
- **false** if the string does not match.

Example:

~~~text
'12345' matches '[0-9]{5}'
'AB-1234' matches '[A-Z]{2}-[0-9]{4}'
'hello' matches '[a-z]+'
~~~

All three examples return true. The first example requires exactly five digits; the second example requires two uppercase letters, a hyphen, and four digits; the last example requires one or more lowercase letters.

**matches checks the entire string**, corresponding to the full-match operation of Java regular expressions. The pattern **[0-9]{5}** does not accept the string **Code 12345**, even though it contains a five-digit segment inside. To allow a prefix or suffix, include them explicitly in the pattern, or use a substring search mechanism in Java if that is the actual goal.

Anchors **^** and **$** can also be written to make the intent explicit:

~~~text
'12345' matches '^[0-9]{5}$'
~~~

With the matches operator, full-string matching is already required; anchors remain useful when readers are familiar with regular expression syntax and want to express expected boundaries clearly.

## 2. SpEL Uses Java Regular Expressions

SpEL uses Java's regular expression syntax, provided by the Pattern class in the java.util.regex package. Therefore, Java Pattern rules for character classes, quantifiers, groups, alternation, and flags also apply to the matches operator.

Some common constructs:

| Construct | Meaning | Example |
|---|---|---|
| **[0-9]** | A digit from 0 to 9 | **[0-9]{4}** |
| **[A-Z]** | An uppercase ASCII letter | **[A-Z]+** |
| **[a-z]** | A lowercase ASCII letter | **[a-z]+** |
| **[A-Za-z]** | An uppercase or lowercase ASCII letter | **[A-Za-z]+** |
| **.** | Any single character, excluding line terminators in default mode | **A.B** |
| **+** | One or more times | **[0-9]+** |
| **\*** | Zero or more times | **[A-Z]\*** |
| **?** | Zero or one time | **colou?r** |
| **{n}** | Exactly n times | **[0-9]{6}** |
| **{m,n}** | From m to n times | **[A-Z]{2,4}** |
| **(...)** | Groups components | **(AB)** |
| **^ and $** | Start and end of string anchors in regex | **^[A-Z]+$** |

The vertical bar in regex represents alternation, meaning a choice between branches. For example, **(red|blue)** accepts either word. Characters such as dot, parentheses, plus, and asterisk have special meaning. If you want to treat them as literal characters, escape them according to Java Pattern syntax or place them in an appropriate character class.

### Character class

A character class describes a single character belonging to a given set:

~~~text
[A-Z]
[a-z]
[0-9]
[A-F0-9]
~~~

Character ranges can be combined:

~~~text
[A-Za-z0-9]
~~~

The pattern above accepts ASCII letters and digits. It does not automatically include accented letters from other languages. If business logic needs Unicode support, choose a pattern and Unicode policy suited to it instead of assuming **[A-Za-z]** covers all personal names or international text.

### Quantifier

A quantifier specifies how many times a component appears:

~~~text
[0-9]{5}
[A-Z]{2,4}
[A-Za-z0-9]+
~~~

- **[0-9]{5}** requires exactly five digits.
- **[A-Z]{2,4}** requires from two to four uppercase letters.
- **[A-Za-z0-9]+** requires at least one ASCII letter or digit.

Choose limits that have business meaning. The pattern **[0-9]+** accepts strings of arbitrary length, whereas postal codes, order codes, or branch codes usually have clearly defined lengths.

### Group and alternation

Parentheses group components, while the vertical bar represents choice:

~~~text
(AB|CD)-[0-9]{4}
~~~

The pattern accepts a code starting with AB or CD, followed by a hyphen and four digits. Multiple groups can be combined, but keep the structure readable and avoid nesting too deeply.

### Flag

Java Pattern supports flags to alter matching behavior. For example, the inline flag **(?i)** makes the following part of the pattern case-insensitive:

~~~text
'Spring' matches '(?i)spring'
~~~

Only enable flags when business rules require them. If matching must be case-sensitive, do not add **(?i)** just to make the pattern match more easily.

## 3. Format Validation Examples

### Code consisting of two letters and four digits

~~~text
'AB-1234' matches '[A-Z]{2}-[0-9]{4}'
~~~

The result is true. Values such as **ab-1234**, **ABC-1234**, **AB1234**, or **AB-123** do not match because they differ in letter case, length, or separator.

### Code consisting of exactly six digits

~~~text
'012345' matches '[0-9]{6}'
~~~

The result is true. The leading 0 is preserved because the input is a string. If a code is converted to a numeric type before checking, leading zeros can be lost; identifiers should generally be handled as Strings.

### Simple username

~~~text
'lan_2026' matches '[A-Za-z][A-Za-z0-9_]{2,19}'
~~~

The pattern requires the first character to be an ASCII letter, followed by two to nineteen letters, digits, or underscores. The total length therefore falls between three and twenty characters.

This is only a sample username rule. Real requirements may need to allow hyphens, Unicode, or other characters. Define the policy before choosing the pattern.

### Code with one of two prefixes

~~~text
'INV-2026-0012' matches '(INV|ORD)-[0-9]{4}-[0-9]{4}'
~~~

The pattern accepts the INV or ORD prefix, a four-digit year, and a four-digit sequence number. When there are multiple code categories, alternation helps express the allowed choices in a single pattern.

### Checking whitespace

~~~text
'Hello World' matches '[A-Za-z]+[ ][A-Za-z]+'
~~~

This pattern accepts strictly two groups of ASCII letters separated by a single space. It does not accept multiple spaces, tabs, or more than two words. If other whitespace types are needed, choose the corresponding Java Pattern character class and test with real data.

## 4. Using matches with Root Objects and Variables

The left side of matches can be a property of the root object or a variable in the EvaluationContext.

Example with a variable:

~~~text
#postalCode matches '[0-9]{5}'
~~~

Example with a property:

~~~text
customer.code matches '[A-Z]{2}-[0-9]{4}'
~~~

Example with an object passed in as the root:

~~~java
public class Customer {
    private String code;

    public String getCode() {
        return code;
    }
}
~~~

The expression **code matches '[A-Z]{2}-[0-9]{4}'** reads the code property of the root Customer and checks the format.

Evaluating in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#postalCode matches '[0-9]{5}'");

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("postalCode", "10001");

Boolean valid = expression.getValue(context, Boolean.class);
~~~

The postalCode variable is supplied via the context, while the result is requested as a Boolean. Explicitly specifying the result type helps the application and tests reflect the expression's contract accurately.

If the pattern is also supplied via a variable, you can write:

~~~text
#value matches #pattern
~~~

This is useful when the application manages a configurable set of patterns. However, the source, length, and complexity of the pattern must be controlled. An unrestricted pattern can cause high processing costs or unintended behavior.

## 5. Combining matches with Logical Operators

matches returns a Boolean so it can be combined with **and**, **or**, and **not**.

Example checking both presence of data and format:

~~~text
#code != null and #code matches '[A-Z]{2}-[0-9]{4}'
~~~

The expression only checks the pattern when code is not null. The and operator in SpEL evaluates conditionally, so the right side does not need to be evaluated when the left side is already false.

If a null value is considered valid because the field is optional, it can be expressed as:

~~~text
#optionalCode == null or #optionalCode matches '[A-Z]{2}-[0-9]{4}'
~~~

The expression returns true when the field is not provided or when the value has a valid format. Clearly distinguish mandatory fields from optional fields; these two policies should not share the same expression.

Multiple conditions can be combined:

~~~text
#age >= 18 and #memberCode matches '[A-Z]{2}[0-9]{6}'
~~~

The expression requires age to be at least 18 and memberCode to have two uppercase letters followed by six digits. Use parentheses when an expression has multiple and/or branches to make condition grouping explicit.

Negating the result with the not operator:

~~~text
not (#code matches '[A-Z]{2}-[0-9]{4}')
~~~

The expression returns true when code does not match the pattern. If code can be null or non-String, handle those cases before negating; an evaluation error is not equivalent to a false result.

## 6. Data Types and Common Errors

The matches operator is designed to check strings. Ensure the left side evaluates to a String and the right side provides a valid String pattern.

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Expression fails to parse | Invalid SpEL syntax or unbalanced quotes in literal | Check operators, quotes, and both operand expressions |
| Error when evaluating pattern | Invalid regular expression | Verify Java Pattern syntax independently |
| Left side is not a String | Property/variable is numeric, Boolean, or another object | Convert intentionally in Java or use an appropriate String property |
| null value causes an error | Left side has no string to match against | Check for null before using matches |
| String contains a matching segment but returns false | matches requires matching the entire string | Write a pattern covering the entire accepted format |
| Only letter case is wrong | Pattern is case-sensitive by default | Determine the policy and consider the **(?i)** flag |
| Unexpected result with dots or hyphens | Characters have special meaning in regex | Escape characters or use an appropriate character class |

### Distinguishing syntax errors from evaluation errors

A parse error occurs when SpEL cannot parse the expression string. For example, missing a closing quote or misplacing an operator can fail before the expression runs.

An evaluation error occurs after the expression has parsed, when runtime data or pattern is unsuitable. For example, a property returns null, the data type is not String, or a dynamic pattern is invalid.

Validate patterns when loading configuration rather than waiting for the first live request. When storing patterns in an admin system, validate them before allowing activation.

## 7. Escaping and Quotes

The pattern is placed inside a SpEL String literal, usually using single quotes:

~~~text
#code matches '[A-Z]{2}-[0-9]{4}'
~~~

There are two syntax layers to keep in mind when expressions are written in Java code:

1. Java processes the source string before passing the content to the SpEL parser.
2. SpEL processes the String literal and then passes the pattern to the Java regular-expression engine.

Therefore, a backslash in a pattern may need to be escaped at both layers. If unsure what the final string is, inspect the expression string value right before parsing and test the pattern independently with Java Pattern.

For simple cases, character classes can help avoid hard-to-read escapes. For example, **[.]** represents a literal dot without writing an escape. Even so, do not alter a pattern solely to avoid escaping if doing so makes the intent harder to understand.

If the pattern contains a single quote, handle it according to SpEL String literal rules. Write tests for the exact expression string after Java constructs it, because bugs can reside in string construction rather than in the regex.

## 8. Safety and Performance

Regular expressions can become expensive when patterns are complex and inputs are long. Certain nested repetitions or ambiguous branches can cause matching time to grow sharply on crafted inputs. This risk is commonly called regular-expression denial of service (ReDoS).

To reduce risk:

- Only use patterns controlled by the application or already validated.
- Limit input length before evaluation.
- Limit the length and complexity of configurable patterns.
- Avoid nested quantifiers or overlapping branches that can create excessive backtracking paths.
- Use specific patterns with bounded character counts instead of overly broad patterns.
- Test evaluation time with boundary data and large inputs.
- Do not allow end users to submit arbitrary patterns into a broadly privileged context without a control policy.

Java Pattern does not provide a direct per-call timeout parameter for matches. Therefore, do not rely on an assumed timeout to protect the application. If patterns come from users or administrators, restrict the allowed expression language and consider alternative checks with clear resource limits.

Do not use regex to replace all forms of validation. For email addresses, URLs, phone numbers, addresses, or data with complex business rules, a simple pattern usually checks only part of the format. Combine with an appropriate parser or validation library when deeper semantic checks are needed.

## 9. Testing matches Expressions

A good test should cover valid values, invalid values, and pattern boundaries.

Example:

~~~java
@Test
void matchesPostalCodePattern() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#postalCode matches '[0-9]{5}'");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("postalCode", "10001");
    assertEquals(Boolean.TRUE, expression.getValue(context, Boolean.class));

    context.setVariable("postalCode", "1000A");
    assertEquals(Boolean.FALSE, expression.getValue(context, Boolean.class));
}
~~~

In the test, the same Expression is evaluated with two different values. This verifies both the pattern and variable retrieval from the context.

For each pattern, test cases aligned with business requirements:

| Test Group | Example with two-letter and four-digit code |
|---|---|
| Valid value | **AB-1234** |
| Lowercase | **ab-1234** |
| Missing character | **A-1234** |
| Extra character | **ABC-1234** |
| Wrong separator | **AB_1234** |
| Extra prefix outside format | **Code AB-1234** |
| Extra suffix outside format | **AB-1234-extra** |
| Empty value | Empty string |
| null value | Test null branch before matches |
| Excessively long input | String exceeding business limit |

For Unicode patterns, test accented letters, combining characters, and normalization forms if data may arrive from multiple systems. Two visually identical strings can have different Unicode encodings.

If patterns are stored outside source code, include a syntax check step before activation. Pattern versions, change timestamps, and owners can be recorded for traceability when validation results change.

## 10. Workflow for Adopting a Pattern

When adding or modifying a matches rule:

1. **Describe the format in words.** Clearly state allowed characters, length, order, and case sensitivity.
2. **Write valid and invalid examples.** Examples help catch missed cases before writing the regex.
3. **Write the simplest pattern meeting the requirements.** Use character classes, quantifiers, and groups with clear bounds.
4. **Verify the pattern with Java Pattern.** Confirm syntax and behavior against the prepared examples.
5. **Place the pattern into the SpEL expression.** Verify quotes, escaping, variables, and the Boolean result type.
6. **Test in a realistic EvaluationContext.** Use the same root object, variables, and context configuration as the application.
7. **Evaluate processing cost.** Try long inputs and boundary cases to spot patterns that may cause heavy backtracking.
8. **Deploy under control.** If the pattern is managed outside source code, store the previous version and have a rollback path if the new rule causes failures.

When a rule changes, compare the accepted input set before and after the change. A small change in a quantifier or alternation can significantly widen or narrow the set of valid values.

## 11. Review Checklist

Before accepting an expression using matches, verify:

- [ ] The left side always has type String according to the data contract.
- [ ] The right side is a valid regular expression according to Java Pattern.
- [ ] The pattern matches the entire string as required by business rules.
- [ ] Character classes and quantifiers have appropriate bounds.
- [ ] Case sensitivity and Unicode policies have been defined.
- [ ] Null and empty strings are handled intentionally.
- [ ] Quotes and escaping have been verified after constructing the expression string.
- [ ] Valid values, invalid values, boundaries, and overly long inputs are tested.
- [ ] Dynamic patterns are validated and source-controlled.
- [ ] Regex complexity does not introduce unnecessary backtracking risk.
- [ ] The Boolean result is combined with other conditions using accurate logic.

## Conclusion

The matches operator lets SpEL test a string using a Java regular expression and return a Boolean. Because matching requires the entire string, the pattern must describe the full allowed format. Choose bounded character classes and quantifiers, handle null and data types before matching, verify escaping across both Java and SpEL, and test patterns with boundary data. When patterns are externally configured, control their source and complexity to avoid turning a simple validation rule into a performance risk.
