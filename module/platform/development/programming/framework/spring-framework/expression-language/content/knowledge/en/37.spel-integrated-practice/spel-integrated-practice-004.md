# Building Conditional Expressions with Elvis and the Ternary Operator

## 1. Purpose of conditional expressions

Spring Expression Language (SpEL) supports conditional operators to select values based on runtime data. Two commonly used syntaxes are:

- **Ternary operator:** condition ? valueIfTrue : valueIfFalse.
- **Elvis operator:** value ?: defaultValue.

Ternary is suitable when you need to choose between two branches based on a Boolean condition. Elvis is suitable when you need a default value if the left-hand expression does not have a useful value.

For example:

    #score >= 50 ? 'PASS' : 'FAIL'

    #customerName ?: 'Guest'

The first expression decides between PASS or FAIL. The second expression returns customerName if it has a suitable value, otherwise Guest.

The two operators serve different purposes. Choose the syntax based on the decision you want to express instead of trying to cram every case into one long expression.

## 2. Ternary operator: condition ? trueValue : falseValue

General syntax:

    condition ? valueIfTrue : valueIfFalse

SpEL evaluates condition. If the result is true, the expression returns valueIfTrue; if false, it returns valueIfFalse.

For example:

    #age >= 18 ? 'ADULT' : 'MINOR'

If age is 20, the result is ADULT. If age is 16, the result is MINOR.

Numeric example:

    #quantity > 0 ? #price * #quantity : 0

If quantity is greater than 0, the expression computes the line total. Otherwise, the result is 0.

The condition must yield a Boolean value or a value that can be appropriately converted to Boolean according to the EvaluationContext. If the condition is null or cannot be evaluated as a Boolean, evaluation can fail.

## 3. Complete Java example with EvaluationContext

You can parse an expression once and evaluate it with different variables.

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression(
            "#score >= #passMark ? 'PASS' : 'FAIL'"
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("score", 82);
    context.setVariable("passMark", 60);

    String result =
        expression.getValue(context, String.class);

    // result = "PASS"

Change the data:

    context.setVariable("score", 45);

    String nextResult =
        expression.getValue(context, String.class);

    // nextResult = "FAIL"

The expression source does not change. Each time getValue is called, SpEL evaluates the condition using the current variable values and picks exactly one result branch.

This usage is easy to test and avoids concatenating input data into the expression source.

## 4. Two branches can return values of different types

Ternary returns the value of the chosen branch. The two branches can be different expressions, but they should have result types compatible with the intended usage.

For example:

    #active ? 'ENABLED' : 'DISABLED'

Both branches return String.

For example:

    #hasDiscount ? #discountAmount : 0

One branch may return BigDecimal while the other is an integer. SpEL may apply type conversion depending on the context and target type, but you should not rely on implicit conversion if the result type matters.

You can specify the target type when calling getValue:

    BigDecimal amount =
        expression.getValue(context, BigDecimal.class);

If the two branches are incompatible, conversion can fail. Use literals and variables with consistent types, or convert explicitly before returning the result.

## 5. Elvis operator: value ?: defaultValue

Elvis is a shorthand for cases where you want to use a default value when the left-hand side does not have a suitable value.

Syntax:

    expression ?: defaultValue

For example:

    #displayName ?: 'Anonymous'

If displayName has a value, the expression returns that value. If displayName is null or an empty string, Elvis returns Anonymous.

An equivalent idea using ternary:

    #displayName != null and #displayName != ''
        ? #displayName
        : 'Anonymous'

Elvis avoids repeating the same expression in both the condition and the true branch.

Java example:

    context.setVariable("displayName", null);

    Expression expression =
        parser.parseExpression(
            "#displayName ?: 'Anonymous'"
        );

    String result =
        expression.getValue(context, String.class);

    // result = "Anonymous"

Elvis is especially useful when reading optional properties or variables and needing a fallback value.

## 6. Elvis handling of null and empty strings

In SpEL, Elvis chooses the right-hand side when the left-hand side is null or an empty string.

For example:

    #name ?: 'Unknown'

Cases:

| Name value | Result |
| --- | --- |
| 'Lan' | 'Lan' |
| null | 'Unknown' |
| '' | 'Unknown' |
| '   ' | '   ' |

A string containing only whitespace is not an empty string, so Elvis keeps that value as-is.

If business rules treat whitespace-only strings as missing data, normalize with trim() or check isBlank() before applying the default:

    #name != null and !#name.isBlank()
        ? #name
        : 'Unknown'

Or normalize in Java before putting the variable into the context.

Elvis does not automatically treat every empty collection as null. An empty List or Map is still a collection object. If you need a fallback for an empty collection, check isEmpty() explicitly.

## 7. Elvis with nullable properties

Suppose the customer object has a nullable nickname property.

You can write:

    #customer.nickname ?: #customer.name

If nickname has a value, use nickname. If null or empty, use name.

If customer can also be null, protect the path:

    #customer?.nickname ?: 'Guest'

Safe navigation returns null when customer is null; Elvis then selects Guest.

With multiple property levels:

    #customer?.profile?.displayName ?: 'Guest'

This expression avoids errors when customer or profile is null, and picks the default value if displayName is null or empty.

Distinguish null on an intermediate object from a null value on the final property. Safe navigation handles a null receiver; Elvis handles a left-hand result lacking a suitable value.

## 8. Combining ternary with logical operators

The ternary condition can be a Boolean expression combining AND, OR, and NOT.

For example:

    #customer.active and #order.total >= #minimum
        ? 'APPROVED'
        : 'REVIEW'

Parentheses can be used to clarify condition grouping:

    (#customer.active and #customer.verified)
        ? 'TRUSTED'
        : 'CHECK_REQUIRED'

If a condition is long, put each group on its own line and use explicit parentheses.

AND and OR follow short-circuit rules. Once the outcome is determined, SpEL does not need to evaluate the remainder of the same logical operation. This is useful when the second side is only valid if the first side confirms the object exists.

For example:

    #customer != null and #customer.active
        ? 'ACTIVE'
        : 'INACTIVE'

If customer is null, the second side of AND is not evaluated.

## 9. Combining Elvis and ternary

Elvis can be used to normalize a value before using ternary, or ternary can choose between conditional values.

For example:

    (#customer?.membershipLevel ?: 'STANDARD') == 'GOLD'
        ? 'PREMIUM_SHIPPING'
        : 'NORMAL_SHIPPING'

First, the expression retrieves membershipLevel. If null or empty, it uses STANDARD. Then it compares against GOLD and selects the result.

Another example:

    #order?.total ?: 0

The expression returns total if it has a value, otherwise 0. It can be placed inside a calculation:

    (#order?.total ?: 0) >= #freeShippingThreshold
        ? 'FREE'
        : 'CHARGED'

Use parentheses when combining multiple operators so readers clearly understand the processing order and avoid precedence mistakes.

## 10. Using ternary for display labels or statuses

Ternary fits simple decisions with two outcomes.

Order status example:

    #paid ? 'PAID' : 'UNPAID'

Display permission example:

    #isAdmin ? 'FULL_ACCESS' : 'READ_ONLY'

Quantity-based label example:

    #stock > 0 ? 'IN_STOCK' : 'OUT_OF_STOCK'

If more than two states are needed, nested ternary can be used, though moving to a Java method or mapping should be considered.

Three-state example:

    #stock > 10
        ? 'AVAILABLE'
        : (#stock > 0 ? 'LOW_STOCK' : 'OUT_OF_STOCK')

This expression is still short and has a clear purpose. As the number of branches grows, nested ternaries become hard to maintain.

## 11. Avoiding deeply nested ternaries

An expression like:

    #score >= 90
        ? 'EXCELLENT'
        : #score >= 80
            ? 'GOOD'
            : #score >= 60
                ? 'PASS'
                : 'FAIL'

can run, but becomes harder to read when adding conditions or changing threshold order.

For multiple classification levels, move the logic to Java:

    String classifyScore(int score) {
        if (score >= 90) {
            return "EXCELLENT";
        }
        if (score >= 80) {
            return "GOOD";
        }
        if (score >= 60) {
            return "PASS";
        }
        return "FAIL";
    }

If the rule needs dynamic configuration, you can expose a small, pure, clearly named function:

    #classifyScore(#score)

Do not turn an expression into a multi-branch program just to avoid writing Java.

## 12. Elvis with collections and Maps

Elvis does not treat every empty collection as missing data.

For example:

    #members ?: {}

If members is null, the result is an empty List. However, if members is already an empty List, Elvis keeps that List; it does not replace it just because the collection has no elements.

If you want a fallback when a List is empty:

    #members != null and !#members.isEmpty()
        ? #members
        : #defaultMembers

With a Map:

    #settings != null and !#settings.isEmpty()
        ? #settings
        : {:}

If you only want a default when the Map is null, you can use:

    #settings ?: {:}

Distinguish the three states:

- Null: no collection object exists.
- Empty: the collection exists but has no elements.
- Non-empty: the collection has at least one element.

Choose the condition matching the exact business meaning.

## 13. Combining with selection and projection

Ternary or Elvis can be used on the results of selection/projection.

Example choosing the resulting collection or fallback:

    #orders.?[status == 'PAID'] ?: {}

Selection returns a List of matching orders. If there are no results and the collection is null, Elvis can supply a default empty List.

Example getting the first valid customer name:

    #customers.?[active == true].![name][0] ?: 'Unknown'

However, accessing index [0] on an empty collection can raise an error before Elvis receives a result. Elvis does not protect an index operation that has already failed.

Check the collection first or use select first:

    #customers.^[active == true]?.name ?: 'Unknown'

This approach retrieves the first active element, uses safe navigation if no element exists, and selects Unknown when the result is null or empty.

For large collections, consider the cost of selection/projection and creating intermediate collections. If only one element is needed, select first usually expresses intent better.

## 14. Controlling types and null values

When using Elvis or ternary, clearly determine the type of each branch and the result type.

For example:

    #discount != null ? #discount : 0

If discount is BigDecimal while 0 is Integer, conversion may be required when the caller retrieves the result as BigDecimal.

A clearer approach:

    #discount != null
        ? #discount
        : T(java.math.BigDecimal).ZERO

Or normalize the data type in Java:

    context.setVariable(
        "discount",
        discount != null ? discount : BigDecimal.ZERO
    );

    BigDecimal result =
        parser.parseExpression("#discount")
            .getValue(context, BigDecimal.class);

For monetary values, use BigDecimal with clear scale/rounding rules. Avoid mixing Integer, Double, and BigDecimal across branches if calculations require financial precision.

If a value can be null, decide whether null means missing data, invalid data, or a default value. Do not use Elvis to silently turn a data error into a valid value when the business logic requires reporting an error.

## 15. Operator precedence and parentheses

Expressions with multiple operators are parsed according to SpEL's precedence rules. When combining ternary, Elvis, AND, OR, comparisons, and arithmetic operations, use parentheses to show intent.

For example:

    (#active and #verified)
        ? (#discount ?: 0)
        : 0

This expression:

1. Checks active and verified.
2. If both are true, takes discount or 0 if missing.
3. If the condition is false, returns 0.

If parentheses are omitted in a complex expression, readers may misunderstand the evaluation order even though the parser still follows deterministic rules.

Do not rely on memorizing precedence when a pair of parentheses can make the intent clear.

## 16. Separating conditions and default values for easier testing

For important rules, keep the source fixed and pass variables via EvaluationContext.

For example:

    Expression expression =
        parser.parseExpression(
            "#active and #verified"
                + " ? (#displayName ?: 'Guest')"
                + " : 'ACCESS_DENIED'"
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("active", true);
    context.setVariable("verified", true);
    context.setVariable("displayName", "");

    String result =
        expression.getValue(context, String.class);

    // result = "Guest"

Cases can be tested individually:

- Both active and verified are true, displayName has content.
- Both active and verified are true, displayName is null.
- Both active and verified are true, displayName is empty.
- Either condition is false.
- A required variable has not been registered.
- Variable type is incompatible.

If an expression grows so long that writing tests for each branch becomes difficult, extract facts or multi-step logic into Java.

## 17. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Ternary reports condition error | Condition is null or cannot be converted to Boolean | Check type and null before use |
| Wrong branch chosen | Unclear condition or AND/OR grouping | Use parentheses and verify each condition |
| Elvis does not apply fallback for empty List | An empty collection is not synonymous with null | Check isEmpty() |
| Elvis keeps whitespace string | The string is not empty | trim or isBlank before choosing default |
| Index fails before Elvis | Indexer failed before Elvis ran | Check size or use select first with safe navigation |
| Conversion error across two branches | Incompatible result types | Use consistent types or explicit conversion |
| Nested ternary is hard to read | Too many branches | Move to a Java method or mapping |
| Default hides data error | Using Elvis for required fields | Validate and report error instead of silently falling back |
| Variable not found | Not registered or misspelled name | Check EvaluationContext |

When debugging, separate the condition from the result branches, inspect each variable's value, and verify the type of the expression on the left-hand side of Elvis.

## 18. Key points to remember

- Ternary has the syntax condition ? trueValue : falseValue.
- Ternary selects exactly one branch based on a Boolean condition.
- Elvis has the syntax value ?: defaultValue.
- Elvis chooses the default when the left-hand side is null or an empty string.
- A whitespace-only string is not an empty string.
- An empty collection does not automatically trigger Elvis; use isEmpty() when needed.
- Safe navigation protects operations on a null receiver; Elvis handles null/empty results on the left-hand side.
- An indexer can fail before Elvis is evaluated; check the collection before accessing an index.
- Both branches of a ternary should return types compatible with the caller.
- Use parentheses to clarify precedence when combining AND, OR, ternary, and Elvis.
- Avoid multi-level nested ternaries; move multi-branch logic to Java.
- Keep expression sources fixed and pass data through variables.
- Test true, false, null, empty string, whitespace, empty collection, and invalid types.
- Do not use defaults to hide missing required data.

Ternary is suitable for choosing between two results based on a clear decision. Elvis is suitable for providing a fallback for null or empty string values. When combining the two operators, clearly define the condition, data types, and meaning of default values so expressions remain readable, testable, and never hide business errors.

## References

- Spring Framework Reference — The Ternary Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-ternary.html
- Spring Framework Reference — The Elvis Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html
- Spring Framework Reference — Operators: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html
- Spring Framework Reference — Safe Navigation Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html
- Spring Framework Reference — Collection Selection and Projection: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html
