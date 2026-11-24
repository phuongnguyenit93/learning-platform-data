# Elvis with Empty Strings, Null, and False Values

## 1. What Is the Elvis Operator Used For?

Spring Expression Language (SpEL) provides the Elvis operator \`?:\` to choose a default value when the left-hand value has no suitable content.

Syntax:

    value ?: defaultValue

SpEL evaluates the left-hand side first. If the left-hand side has an acceptable value, the result is that value. If the left-hand side is \`null\` or an empty string \`""\`, the result is the right-hand side.

Example:

    #displayName ?: 'Guest'

The expression above returns \`Guest\` if \`#displayName\` is null or an empty string. If there is a name, the expression returns that name itself.

Elvis helps shorten cases where you would normally have to write conditions checking for null or an empty string. However, it is important to understand clearly which values are considered missing. In particular, Boolean \`false\` is not a missing value for this operator.

## 2. Behavior with Null

When the left-hand side is \`null\`, Elvis returns the right-hand side.

    null ?: 'Unknown'

Result:

    Unknown

Example with a variable:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("#name ?: 'Unknown'");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("name", null);

    String result =
        expression.getValue(context, String.class);

    // result = "Unknown"

If the variable has a value:

    context.setVariable("name", "Lan");

    String result =
        expression.getValue(context, String.class);

The result is:

    Lan

Elvis does not change the variable's value. It only chooses the return value for the expression being evaluated.

If the expression accesses a property through an intermediate object that may be null, consider safe navigation before applying Elvis. For example:

    #customer?.name ?: 'Guest'

If \`#customer\` is null, safe navigation returns null and Elvis selects \`Guest\`. If you omit safe navigation:

    #customer.name ?: 'Guest'

then accessing \`name\` can fail immediately when \`#customer\` is null; Elvis cannot handle an error that occurs before the left-hand value is produced.

## 3. Behavior with Empty Strings

SpEL also treats an empty string \`""\` as a case that needs the default value.

    '' ?: 'Unknown'

Result:

    Unknown

Example:

    Expression expression =
        parser.parseExpression("#displayName ?: 'Guest'");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("displayName", "");

    String result =
        expression.getValue(context, String.class);

    // result = "Guest"

When the string has content, that value is preserved:

    context.setVariable("displayName", "Spring");

The result is:

    Spring

This point is useful when input data may be null or an empty string, such as a display name, label, short description, or an optional configuration value.

## 4. Whitespace-Only Strings Are Not Empty Strings

Elvis checks for an empty string; it does not automatically trim or check whether the string is blank.

Example:

    '   ' ?: 'Unknown'

The left-hand side is a string with three space characters, so it is not an empty string. The result remains the whitespace string, not \`Unknown\`.

This is an important distinction when handling form data or user input. A string containing only spaces may look like it has no content, yet Elvis still preserves it.

If business logic needs to treat whitespace-only strings as missing as well, check explicitly:

    #name != null and !#name.trim().isEmpty()
        ? #name
        : 'Unknown'

The null check comes before calling \`trim()\`. Thanks to AND short-circuiting, the right-hand side does not need to be evaluated when \`#name\` is null.

In Java environments supporting \`String.isBlank()\`, you can use that method to express the blank rule more clearly:

    #name != null and !#name.isBlank()
        ? #name
        : 'Unknown'

Choose the rule that matches the data requirement: empty strings only, or blank strings as well.

## 5. Behavior with Boolean false

An easy point of confusion is that Elvis does not treat Boolean \`false\` as a missing value.

    false ?: true

The result is still:

    false

Reason: \`false\` is a valid Boolean value. It is neither null nor an empty string.

Example with a variable:

    Expression expression =
        parser.parseExpression("#enabled ?: true");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("enabled", false);

    Boolean enabled =
        expression.getValue(context, Boolean.class);

Result:

    false

If \`#enabled\` is null, the same expression will return true. If \`#enabled\` is false, it still returns false.

This is especially important for configuration flags, on/off states, access permissions, and user choices. Do not use Elvis if business logic wants to treat false as equivalent to not providing a value.

## 6. Comparing Null, Empty Strings, False, and Other Values

The table below summarizes Elvis behavior when using \`'DEFAULT'\` or a corresponding default value on the right-hand side:

| Left-hand value | Does Elvis use the right-hand side? | Reason |
| --- | --- | --- |
| \`null\` | Yes | Null value |
| \`""\` | Yes | Empty string |
| \`"Lan"\` | No | String with content |
| \`"   "\` | No | String with whitespace characters |
| \`false\` | No | Boolean false is a valid value |
| \`true\` | No | Boolean true is a valid value |
| \`0\` | No | Number 0 is a valid value |
| Empty collection | No | Elvis does not treat an empty collection as an empty string |

Examples:

    false ?: true       // false
    0 ?: 10             // 0
    '' ?: 'Unknown'     // Unknown
    null ?: 'Unknown'   // Unknown
    '   ' ?: 'Unknown'  // string of three spaces

Do not assume Elvis works like truthy/falsy operators in JavaScript or some other languages. SpEL has specific rules: null and empty strings are replaced by the right-hand side; Boolean false, the number 0, and empty collections remain their current values.

## 7. How Does Elvis Differ from the Ternary Operator?

The ternary operator has the form:

    condition ? valueIfTrue : valueIfFalse

It selects one of two branches based on a boolean condition.

Example:

    #score >= 80 ? 'Pass' : 'Fail'

If the score is at least 80, the result is \`Pass\`; otherwise, it is \`Fail\`.

Elvis has the form:

    value ?: defaultValue

It does not take a separate boolean condition. It checks whether the left-hand value is null or an empty string.

| Criterion | Ternary | Elvis |
| --- | --- | --- |
| Syntax | \`condition ? a : b\` | \`value ?: default\` |
| Purpose | Choose a branch based on a condition | Provide a fallback value for null/empty string |
| With false | Acts as a false condition if used as condition | Preserves false if false is the left-hand side |
| With empty string | Depends on the condition written by the author | Uses the right-hand side |
| With null | Depends on the condition and comparison | Uses the right-hand side |

If you need a default for a Boolean only when null while still preserving false, you can use Elvis:

    #enabled ?: true

Or use ternary to state the condition explicitly:

    #enabled != null ? #enabled : true

Both approaches preserve false and only use true when the value is null.

If business logic wants to treat false as a case requiring replacement as well, write an explicit condition instead of using Elvis:

    #enabled == true ? #enabled : #defaultEnabled

This expression returns \`#defaultEnabled\` when \`#enabled\` is false or null. The boolean condition must accurately reflect the business rule.

## 8. Using Elvis with Object Properties

Elvis is often used to create a default value when reading a property that may be null or empty.

Example where the root object is Customer:

    public class Customer {
        private String displayName;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }

Evaluation:

    Expression expression =
        parser.parseExpression("displayName ?: 'Guest'");

    String result =
        expression.getValue(customer, String.class);

If \`displayName\` is null or \`""\`, the result is \`Guest\`. If the property has an actual name, the result is that name.

With nested properties, you need to handle the possibility of a null intermediate object:

    address?.city ?: 'Unknown'

Safe navigation allows the expression to return null when address does not exist, after which Elvis can choose the default value.

If you only write:

    address.city ?: 'Unknown'

then accessing \`city\` still requires the \`address\` object. When address is null, evaluation may raise an error before Elvis receives a value.

## 9. Using Elvis in SpEL Templates and Spring Annotations

Elvis can appear inside a SpEL template:

    Expression template = parser.parseExpression(
        "Hello #{#displayName ?: 'Guest'}!",
        new TemplateParserContext()
    );

    String message =
        template.getValue(context, String.class);

If \`#displayName\` is null or an empty string, the template produces:

    Hello Guest!

If there is a name, that name is inserted into the string.

In Spring integration points that support SpEL, Elvis can be used in annotations:

    @Value("#{systemProperties['app.user'] ?: 'Guest'}")
    private String userName;

Spring evaluates the expression during bean processing. If the system property is null or an empty string, the field receives \`Guest\`.

Remember that this is behavior at a Spring integration point that processes expressions. If you merely store the same string in an ordinary Java string, SpEL does not run automatically.

## 10. Using Elvis with Operations and Combined Expressions

The left-hand side of Elvis can be a complex expression, as long as the result can be checked under Elvis rules.

Example:

    (#order?.customer?.displayName) ?: 'Guest'

Or:

    (#config?.label) ?: 'Default label'

Use parentheses when an expression has multiple operators or multiple access steps so readers can clearly see which part is the left-hand side of Elvis.

Elvis can be combined with ternary:

    (#customer?.name ?: 'Guest') == 'Admin'
        ? 'Administrator'
        : 'User'

In this expression:

1. SpEL retrieves the customer's name if present.
2. If the name is null or empty, Elvis replaces it with Guest.
3. The result is compared with Admin.
4. Ternary chooses the label Administrator or User.

If the expression becomes hard to read, split it into smaller expressions or move the business logic into a clear Java method instead of creating an overly long SpEL string.

## 11. Common Mistakes and Misconceptions

### Thinking false Will Trigger the Default

Wrong expectation:

    #enabled ?: true

If \`#enabled\` is false, the result is still false. Elvis only replaces null or empty strings.

If you want false to use the default as well, write a ternary condition matching the business rule.

### Thinking a Whitespace String Is Empty

    '   ' ?: 'Unknown'

The result is still the whitespace string. If blank needs to be treated as missing, trim or use isBlank in an explicit condition.

### Thinking Elvis Automatically Handles Every Null Reference

    #customer.name ?: 'Guest'

If customer is null, accessing name can fail before Elvis is applied. Use safe navigation:

    #customer?.name ?: 'Guest'

### Confusing Elvis with the OR Operation

Elvis is not a logical OR operation. It chooses a replacement value for null or an empty string; it does not check whether either side is true.

### Using a Default of the Wrong Type

If the expression is expected to return an Integer but the right-hand side is a string, type conversion may fail. Choose a default value compatible with the desired result type.

### Ignoring That Evaluation Can Still Fail

Elvis does not catch every exception thrown while evaluating the left-hand side. A nonexistent property, uncallable method, or object access error can still cause the expression to fail.

## 12. Checking and Debugging

When Elvis returns an unexpected value, check in order:

1. Is the left-hand side actually null, an empty string, false, or another value?
2. Is it a string containing only whitespace rather than being empty?
3. Is any intermediate object null before Elvis is applied?
4. Has the variable been placed into the EvaluationContext?
5. Does the right-hand side have a data type suitable for the desired result?
6. Is the expression being evaluated in the right context?

You can test using small expressions:

    null ?: 'fallback'
    '' ?: 'fallback'
    'Lan' ?: 'fallback'
    false ?: true
    0 ?: 10

These cases help directly confirm the rules for null, empty String, and false without needing a complex object model.

Distinguishing parse errors from evaluation errors is also very helpful. Invalid syntax will fail at parse time; an invalid property or variable usually surfaces only when evaluation needs to access it.

## 13. Points to Remember

- Elvis has the syntax \`value ?: defaultValue\`.
- The right-hand side is used when the left-hand side is null or an empty string.
- Strings with content are preserved.
- Whitespace-only strings are not automatically treated as empty.
- Boolean false is a valid value and does not trigger the default.
- The number 0 and empty collections also do not trigger the default simply because they are empty or zero.
- Use safe navigation when an intermediate object may be null.
- Use ternary when a decision needs to be based on a boolean condition, especially if false is also treated as a case needing special handling.
- Elvis does not replace validation, does not catch all evaluation exceptions, and does not automatically construct an object graph.

When choosing default values in SpEL, clearly define in business terms which states count as missing: null, empty string, blank string, or even Boolean false. Write the expression according to that exact rule to avoid accidentally altering valid data.
