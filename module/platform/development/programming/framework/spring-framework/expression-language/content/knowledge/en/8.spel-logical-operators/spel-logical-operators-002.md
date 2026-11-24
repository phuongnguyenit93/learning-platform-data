# Keyword Form and Symbol Form of Logical Operators

## 1. Two Ways to Write the Same Logical Operation in SpEL

Spring Expression Language (SpEL) supports logical operators to combine boolean conditions or negate a condition. For AND, OR, and NOT, SpEL allows writing in two forms:

- **Keyword form:** `and`, `or`, `not`.
- **Symbol form:** `&&`, `||`, `!`.

These two forms represent the same logical meaning. For example:

    #active and #score >= 80

is equivalent to:

    #active && #score >= 80

Similarly:

    #blocked or #expired

is equivalent to:

    #blocked || #expired

And:

    not #enabled

is equivalent to:

    !#enabled

The keyword form is often easier to read in long expressions or in configurations managed jointly by multiple teams. The symbol form is concise and familiar to those who often write conditions in Java. The important thing is to understand that they are two ways to represent SpEL operators, not two different evaluation mechanisms.

## 2. Operator Comparison Table

| Meaning | Keyword form in SpEL | Symbol form | Result |
| --- | --- | --- | --- |
| AND | `and` | `&&` | true when both sides are true |
| OR | `or` | `||` | true when at least one side is true |
| NOT | `not` | `!` | Inverts the boolean value |

Quick examples:

    true and true       // true
    true && false       // false
    false or true       // true
    false || false      // false
    not false           // true
    !true               // false

The examples above are SpEL expressions. When placed in Java, they are usually passed as a string to the parser:

    Expression expression =
        parser.parseExpression("true && false");

Do not write `and` or `or` as Java operators in an ordinary Java expression. This is syntax that SpEL understands after receiving the string.

## 3. AND: and and &&

AND yields true only when both conditions are true.

| A | B | A AND B |
| --- | --- | --- |
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

The following two expressions are equivalent:

    #customer.active and #customer.verified

    #customer.active && #customer.verified

Full example with variables:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        "#active && #score >= 80"
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("active", true);
    context.setVariable("score", 92);

    Boolean eligible =
        expression.getValue(context, Boolean.class);

The result is `true` because the customer is active and the score meets the threshold of 80.

The expression can be changed to the keyword form without changing its meaning:

    Expression expression = parser.parseExpression(
        "#active and #score >= 80"
    );

Both ways require the combined conditions to yield a suitable boolean result.

### Short-circuiting of AND

AND has short-circuit evaluation behavior: if the left-hand side is already false, the result of the entire expression is definitely false, so the right-hand side does not need to be evaluated.

Example:

    false and #service.isAvailable()

    false && #service.isAvailable()

Because the left-hand side is already false, SpEL does not need to invoke the expression on the right-hand side to decide the result. This is important when the right-hand side may access properties, call methods, or perform costly operations.

Even with short-circuiting, you should not use it to hide an invalid expression or an inappropriate method call. Design conditions so that the left-hand side clearly expresses the condition that needs to be checked first.

## 4. OR: or and ||

OR yields true when at least one of the two conditions is true. Only when both sides are false is the result false.

| A | B | A OR B |
| --- | --- | --- |
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

The following two expressions are equivalent:

    #admin or #owner

    #admin || #owner

Example:

    Expression expression = parser.parseExpression(
        "#admin || #owner"
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("admin", false);
    context.setVariable("owner", true);

    Boolean canManage =
        expression.getValue(context, Boolean.class);

The result is `true` because the user is the owner, even though `admin` is false.

### Short-circuiting of OR

OR also evaluates with short-circuiting. If the left-hand side is already true, the entire expression is definitely true, so the right-hand side does not need to be evaluated.

Example:

    true or #service.isAvailable()

    true || #service.isAvailable()

In both cases, SpEL already knows the result is true from the left-hand side. Skipping the right-hand side helps avoid an unnecessary access.

OR can be used when one of several conditions is sufficient to allow an operation. However, place conditions in an easy-to-understand order and do not rely on side effects from the right-hand side.

## 5. NOT: not and !

NOT is a unary operator that takes a boolean value and inverts the result:

- true becomes false.
- false becomes true.

Two equivalent ways to write it:

    not #locked

    !#locked

Example:

    Expression expression =
        parser.parseExpression("!#locked");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("locked", false);

    Boolean canEdit =
        expression.getValue(context, Boolean.class);

The result is `true` because the account is not locked.

NOT applies to expressions according to operator precedence. When conditions are complex, use parentheses to clarify the negation scope:

    not (#admin or #owner)

    !(#admin || #owner)

The two forms above negate the entire result of the OR operation. Writing:

    !#admin || #owner

only negates `#admin` before performing OR with `#owner`. This is different logic.

## 6. Precedence and Parentheses

When combining multiple operators, SpEL applies precedence. For the logical operators under consideration, an easy-to-remember order is:

1. NOT (`not` or `!`) is processed first.
2. AND (`and` or `&&`) is processed before OR.
3. OR (`or` or `||`) is processed last.

Example:

    #active and #score >= 80 or #admin

is logically interpreted as equivalent to:

    (#active && (#score >= 80)) || #admin

If `#admin` is true, the overall condition can be true even if the customer is not active or the score is not met. If the business requirement is that the user must be active and (meet the score or be an admin), it needs to be written explicitly:

    #active and (#score >= 80 or #admin)

Parentheses help accurately represent condition groups. You should not rely on readers inferring intent from a long string.

Another example:

    not #suspended and (#verified or #admin)

This condition requires the account not to be suspended and at the same time to be verified or an admin.

Corresponding symbol form:

    !#suspended && (#verified || #admin)

## 7. Mixing Keyword Form and Symbol Form

Because the pairs are equivalent forms, an expression can use both keyword and symbol forms:

    #active and #score >= 80 || #admin

Syntactically, these operators still represent AND and OR. However, mixing two styles in the same expression can make it hard for readers to scan and review.

Choose a unified style for an expression or a group of configurations:

Keyword form:

    #active and (#verified or #admin)

Symbol form:

    #active && (#verified || #admin)

If the development team prioritizes readable expressions in configuration files, the keyword form may be suitable. If expressions are short and the team is already familiar with logical symbols, the symbol form is also clear. Keep a consistent style within the same codebase.

## 8. Distinguishing Logical Operators from Comparison Conditions

Logical operators combine boolean values. Comparison operators produce boolean results that can be fed into AND, OR, or NOT.

Example:

    #age >= 18 and #enabled

In which:

- `#age >= 18` is a comparison expression that returns a boolean.
- `#enabled` is a boolean variable.
- `and` combines the two boolean results.

Symbol form:

    #age >= 18 && #enabled

Multiple comparisons can be combined:

    #age >= 18 and #age <= 65

Or written with parentheses:

    (#age >= 18) and (#age <= 65)

Using parentheses helps readers clearly see each side of the AND operation as a complete condition, especially when the expression has many comparison and arithmetic operators.

Do not confuse `and` with `&` or `or` with `|`. Programming-language bitwise operators and logical operators in SpEL have different purposes. When writing boolean conditions, use the proper pairs `and`/`&&` and `or`/`||`.

## 9. Using Expressions in Spring and Java

SpEL expressions are often created from Java strings. Therefore, the outer quotes belong to the Java string, while the operators inside belong to SpEL syntax.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        "#account.active && (#account.balance >= #minimum || #account.vip)"
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("account", account);
    context.setVariable("minimum", 1_000);

    Boolean permitted =
        expression.getValue(context, Boolean.class);

This structure can be used in a service or a rule evaluation component. Make sure the `account` object has the corresponding properties and the context provides the right variables.

In Spring annotations or configurations that support SpEL, expressions can be written directly according to the syntax of the integration point. Example:

    @Value("#{systemProperties['user.name'] != null && systemProperties['user.name'].length() > 0}")
    private boolean hasOperatingSystemUser;

The expression inside `#{...}` is processed by Spring at the integration point. Do not confuse this with a normal Java string.

## 10. Checking Parsing and Evaluation Errors

Errors related to logical operators can appear at two stages:

| Stage | Example | How to check |
| --- | --- | --- |
| Parsing | Missing operand after `and`, mismatched parentheses, or invalid token combination | Check syntax and position in the string |
| Evaluation | Variable does not exist, property cannot be read, or value cannot be converted to boolean | Check context, root object, accessors, and data types |

Syntax error example:

    parser.parseExpression("#active and");

The expression ends with the AND operator without a right-hand side, so the parser cannot create a valid expression.

Example where parsing succeeds but evaluation may fail:

    Expression expression =
        parser.parseExpression("#active && #score >= 80");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("active", true);
    // Variable score has not been provided yet

    Boolean result =
        expression.getValue(context, Boolean.class);

The syntax can be parsed successfully, but when `#score` needs to be evaluated, the context does not provide the corresponding variable. Distinguish this error from a parser error.

When debugging, determine exactly whether the error occurs at `parseExpression` or `getValue`. Then check each variable and the data types of the condition.

## 11. Security When Evaluating Logical Conditions

A logical expression can still access properties, call methods, or use other capabilities granted through the evaluation context. Therefore, expressions provided by untrusted users should not be evaluated in a context with broad permissions.

Practical principles:

- Do not concatenate untrusted input directly into an expression and then parse and evaluate it.
- Only put necessary variables into the context.
- Use objects with access scopes appropriate to the rule.
- Restrict property accessors and method resolvers when business rules require access control.
- Consider `SimpleEvaluationContext` if only limited data binding is needed.
- Do not rely on short-circuiting to replace access control.

The keyword form and symbol form have the same logical meaning, so changing `and` to `&&` does not make an expression safer. Security depends on the source of the expression and the permissions granted by the context.

## 12. Key Points to Remember

- `and` is equivalent to `&&`; both are AND.
- `or` is equivalent to `||`; both are OR.
- `not` is equivalent to `!`; both are NOT.
- AND is true only when both sides are true; OR is true when at least one side is true; NOT inverts a boolean.
- AND and OR have short-circuit behavior.
- NOT has higher precedence than AND; AND is higher than OR.
- Use parentheses to clearly express condition groups and avoid misunderstandings.
- Logical operators combine boolean results from variables or comparison expressions.
- Successful parsing does not guarantee successful evaluation; the context must still provide valid data.
- Both writing styles have the same semantics; choose a consistent style and restrict evaluation permissions appropriately.

When writing rules in SpEL, prioritize readable conditions, use parentheses at important logic groupings, and keep the context containing only the data the rule actually needs.
