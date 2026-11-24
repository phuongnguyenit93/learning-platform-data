# Differences Between Elvis and Full Ternary Conditional

SpEL has two operators commonly used to select fallback values: Elvis and the full ternary conditional. Both can appear in configuration or in expressions evaluated at runtime, but they solve two different needs.

- **Elvis** concisely writes the rule "use a default value if the left-hand expression is null or an empty string".
- **The ternary conditional** chooses one of two expressions based on the true/false result of an application-defined condition.

Understanding this difference correctly helps avoid accidentally replacing valid values such as false or 0, while helping the expression reflect the true business intent.

## 1. Full Ternary Conditional

The syntax of the ternary conditional operator is:

    condition ? valueWhenTrue : valueWhenFalse

SpEL evaluates condition first. If the condition is true, the expression returns valueWhenTrue; if false, it returns valueWhenFalse.

For example, classifying academic results based on score:

    #score >= 50 ? 'PASS' : 'RETRY'

If score is 75, the result is PASS. If score is 42, the result is RETRY. The condition can be a longer logical expression:

    #score >= 50 and #attendance >= 0.8
        ? 'PASS'
        : 'REVIEW'

The condition here combines both score and attendance rate. The result is only selected after the entire Boolean condition is evaluated.

The ternary operator is suitable when the decision depends on a specific rule: threshold, status, permission, object type, or multiple combined conditions. It is not only for handling null; any valid Boolean condition can control branch selection.

## 2. The Elvis Operator

Elvis has a shorter syntax:

    expression ?: defaultValue

If the left-hand expression evaluates to a value that is not null and not an empty string, SpEL returns that value itself. If the left-hand value is null or an empty string, SpEL returns defaultValue.

Example getting a display name:

    #displayName ?: 'Guest'

If displayName is An, the result is An. If displayName is null or an empty string, the result is Guest.

If written using the full ternary operator, the same rule would require repeating the left-hand expression:

    #displayName != null and #displayName != ''
        ? #displayName
        : 'Guest'

Elvis shortens this exact check pattern. It is especially convenient when you only want to provide a default value for data that may be missing.

## 3. Elvis Is Not a Truthy/Falsy Check

An easy point of confusion is that Elvis does not treat every "empty" or "false" value the way some other programming languages do. In SpEL, Elvis's replacement condition focuses on null and empty strings.

Illustrative cases:

| Left-hand value | Expression | Result |
|---|---|---|
| null | null ?: 'DEFAULT' | DEFAULT |
| Empty string | '' ?: 'DEFAULT' | DEFAULT |
| String An | 'An' ?: 'DEFAULT' | An |
| Whitespace-only string | ' ' ?: 'DEFAULT' | Preserves the space string |
| false | false ?: true | false |
| Number 0 | 0 ?: 10 | 0 |
| Empty list | {} ?: {1, 2} | Preserves the empty list |

Therefore, Elvis does not mean "if the value has no content in any sense, use the default". It does not automatically trim strings, does not treat spaces as an empty string, does not treat false as a missing value, and does not replace an empty collection.

If business rules consider whitespace-only strings invalid, write an explicit condition using trim and a length check, or normalize the data before evaluating the expression.

## 4. Comparing the Same Rule Written Both Ways

Suppose an application displays a username. When the name is absent, the UI needs to use a default label.

Written with Elvis:

    #name ?: 'Anonymous'

Written with the full ternary conditional:

    #name != null and #name != ''
        ? #name
        : 'Anonymous'

Both expressions have the same goal: return the name when there is a valid name under the null/empty string criterion; otherwise, return Anonymous.

If the condition changes, the ternary operator expresses the rule more clearly. For example, only displaying the name when the user is verified:

    #user.verified
        ? #user.name
        : 'Unverified user'

Elvis cannot replace the expression above because the decision depends on the verified property, not on whether name is null or an empty string.

## 5. Elvis Preserves Valid Values Such as false and 0

Consider a configuration for toggling a feature on/off. If the value is not yet configured, the feature defaults to enabled:

    #featureEnabled ?: true

Results:

- If featureEnabled is null, the result is true.
- If featureEnabled is true, the result is true.
- If featureEnabled is false, the result remains false.

This is very important. false is a defined Boolean value, not missing data. If you use a direct Boolean-style check condition, you might accidentally override an operator's choice to disable the feature.

Similarly with numbers:

    #retryLimit ?: 3

If retryLimit equals 0, the result remains 0. This is appropriate when 0 means "do not retry". Elvis only takes 3 when the value is null; the number 0 is not treated as empty.

If the business requirement is to use the default even when the retry count is 0, express that explicitly with the ternary conditional:

    #retryLimit != null and #retryLimit > 0
        ? #retryLimit
        : 3

Here, the condition actively specifies that only positive numbers are accepted.

## 6. Using Elvis with Nullable Property Access

Elvis only processes the value returned by the left-hand expression. If evaluating the left-hand expression already causes an error due to accessing a null object, Elvis cannot fix that error on its own.

For example, the following expression can fail if customer is null:

    #customer.displayName ?: 'Guest'

You can combine the null-safe navigation operator with Elvis:

    #customer?.displayName ?: 'Guest'

The ?. operator accesses displayName safely: if customer is null, the result of the access part is null. Elvis then uses Guest as the default value.

You need to distinguish their roles:

- ?. handles accessing a property when the preceding object may be null.
- ?: handles a null or empty string value after the left-hand expression is evaluated.

The two operators can be combined, but they do not replace each other. If you only use Elvis after an access that can cause a NullPointerException, the default value may never be evaluated.

## 7. Ternary Conditional Can Handle More Cases

The ternary conditional lets you express specific policies. For example, selecting a fee rate based on customer tier:

    #customer.tier == 'GOLD'
        ? #baseFee * 0.8
        : #baseFee

Or selecting a label based on multiple statuses:

    #order.cancelled
        ? 'CANCELLED'
        : (#order.paid ? 'PAID' : 'PENDING')

The second example has a nested ternary operator inside the false branch. Parentheses clarify the order and scope of the sub-expression. However, if the number of branches grows large, the expression becomes hard to read. In that case, move the classification logic into a Java method or a separate processing component.

Elvis can also be used inside a branch of a ternary operator:

    #user.active
        ? (#user.displayName ?: 'Unnamed user')
        : 'Inactive user'

Here, the active condition decides the branch. Inside the true branch, Elvis only provides the default name if displayName is null or an empty string.

## 8. Operator Selection Table

| Need | Should use | Reason |
|---|---|---|
| Use a fallback value when the result is null | Elvis | Short syntax, right for default-value intent |
| Use a fallback value when a string is null or empty | Elvis | Has special handling for empty strings |
| Check a threshold or business condition | Full ternary | Boolean condition is written explicitly |
| Choose a branch based on true/false status | Full ternary | Has two independent result branches |
| Accept false or 0 as configured values | Elvis | false and 0 are preserved |
| Treat 0 or false as cases needing a default | Full ternary | Replacement criteria can be written explicitly |
| Check whitespace-only strings | Full ternary or normalize beforehand | Elvis does not automatically trim strings |

A practical rule is: when the intent is simply "if missing, use default", choose Elvis. When the intent is "if this condition is true choose A, otherwise choose B", choose the full ternary conditional.

## 9. Java Example Evaluating Both Operators

Both expressions can be parsed with the same ExpressionParser. Each expression receives variables from an EvaluationContext:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("name", "");
    context.setVariable("score", 72);

    Expression defaultName =
            parser.parseExpression("#name ?: 'Guest'");

    Expression resultLabel =
            parser.parseExpression(
                    "#score >= 50 ? 'PASS' : 'RETRY'");

    String name = defaultName.getValue(context, String.class);
    String result = resultLabel.getValue(context, String.class);

With the data above, name is Guest because the name variable is an empty string. result is PASS because score is greater than or equal to 50.

The parser creates an Expression from the string. When getValue is called, SpEL reads variables from the context, evaluates the operator, and returns the expression's value. Specifying the result type in getValue helps the application receive the expected type; if the expression may return null or incompatible data, the application needs a clear way to handle it.

In real-world applications, use a context appropriate for the expression operations that need to be performed. If a rule only needs to read simple data, choose a context with restricted permissions. Do not pass untrusted expressions into a context that has permission to invoke beans or broad methods.

## 10. Testing Edge Cases

When building rules with Elvis or ternary, test values that are easily confused:

- null: confirm the default value is used.
- Empty string: confirm Elvis uses the default.
- Whitespace-only string: confirm the string is preserved if there is no trim rule.
- false: confirm Elvis preserves false.
- 0: confirm Elvis preserves the number 0.
- True and false conditions: confirm each branch of the ternary returns the right result.
- Null root object: confirm null-safe navigation is used in the right places if needed.

Do not test only a single normal case. Many configuration bugs appear in edge-case data, especially when false or 0 is a valid user choice.

## Conclusion

Elvis and the full ternary conditional both help select values in SpEL, but they differ in selection criteria. Elvis returns the left-hand value if it is not null and not an empty string; otherwise, it returns the default value on the right. The ternary conditional evaluates a Boolean condition and then chooses one of two result branches.

Elvis is the concise choice for default values. The full ternary operator fits business decisions with explicit conditions. Remember that false, 0, empty collections, and whitespace-only strings are still preserved by Elvis; if you want to treat them as special cases, write explicit conditions.