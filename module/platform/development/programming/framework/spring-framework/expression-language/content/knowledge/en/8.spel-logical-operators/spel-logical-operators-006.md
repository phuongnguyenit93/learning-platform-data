# Grouping Long Conditions with Parentheses in SpEL

In Spring Expression Language (SpEL), logical operators such as `and`, `or`, and `not` combine Boolean expressions into complex conditions. When an expression has multiple branches, parentheses help clarify which group of conditions must be evaluated together. Explicit grouping helps avoid misunderstandings about operator precedence while making expressions easier to read, test, and maintain.

## 1. Why Group Conditions?

A business condition often consists of multiple smaller requirements. For example, a user is allowed access if they are an administrator, or if they are an active editor belonging to the right department:

    #user.role == 'ADMIN' or
        #user.role == 'EDITOR' and
        #user.active and
        #user.department == 'CONTENT'

The expression above can be parsed according to default operator precedence. However, when reading quickly, a maintainer might not realize that the last three conditions form a single AND branch. Parentheses make the intent visible right in the structure:

    #user.role == 'ADMIN' or
        (
            #user.role == 'EDITOR' and
            #user.active and
            #user.department == 'CONTENT'
        )

The second form shows two clear branches: the administrator branch, or the editor branch meeting all remaining requirements.

## 2. Precedence of Logical Operators

In SpEL, `and` has higher precedence than `or`. The `not` operator is a unary operator used to negate a condition. Therefore:

    A or B and C

is interpreted as equivalent to:

    A or (B and C)

If the business rule wants to group `A or B` first and then combine with `C`, it needs to be written explicitly:

    (A or B) and C

These two expressions are not equivalent in all cases. For example, when A=true, B=false, and C=false:

- `A or (B and C)` produces true.
- `(A or B) and C` produces false.

Parentheses therefore carry logical meaning, not just formatting style. They record the business rule that the author wants to apply.

## 3. Combining AND and OR by Business Group

A useful way to organize is to divide a long condition into groups with distinct meanings, then combine those groups with a higher-level operator.

Example: an order is accepted if it has been paid or is payment-exempt, and at the same time the total meets the threshold:

    (
        #order.status == 'PAID' or
        #order.paymentExempt
    )
    and
    #order.total >= 100

The first group describes valid payment status. The second group checks the order value. The entire expression is true only when one of the two payment conditions is true and the total meets the threshold.

Another example consisting of multiple groups:

    (
        #user.role == 'ADMIN' or
        (
            #user.role == 'EDITOR' and
            #user.department == 'CONTENT'
        )
    )
    and
    #user.active
    and
    not (#user.suspended)

The expression can be read in three parts:

1. The user is an ADMIN, or an EDITOR belonging to the CONTENT department.
2. The user is active.
3. The user is not suspended.

Parentheses wrap the OR branch so that the `active` and `not suspended` conditions apply to both user types.

## 4. Grouping Negated Conditions with NOT

When negating a single condition, `not` can be written before that Boolean expression. When negating a group consisting of multiple branches, place the entire group inside parentheses:

    not (
        #account.disabled or
        #account.expired
    )

The expression above means the account is neither disabled nor expired. By De Morgan's laws, it is equivalent to:

    not #account.disabled and
    not #account.expired

Both ways can express the same logic, but negating the whole group is often easier to compare against business requirements phrased as "not belonging to any of the following cases".

A common mistake is placing `not` with the wrong scope:

    not #account.disabled or #account.expired

This expression only negates the disabled state, then ORs with the expired state. It does not mean the account is both not disabled and not expired. When the intent is to negate both cases, use `not (A or B)` or `not A and not B`.

## 5. Using Nested Parentheses for Multi-Level Conditions

For expressions with multiple levels of AND/OR, each pair of parentheses should represent a rule that can be expressed as a short sentence.

For example, a transaction is valid if:

- the creator is the account owner or an authorized person;
- the account is active and not locked;
- the transaction has a positive amount, or belongs to the fee-exempt group.

This can be written as:

    (
        #transaction.ownerId == #currentUser.id or
        #transaction.approvedBy == #currentUser.id
    )
    and
    (
        #account.active and
        not (#account.locked)
    )
    and
    (
        #transaction.amount > 0 or
        #transaction.feeExempt
    )

The groups are joined by AND at the outer level. Inside each group, OR or AND describes its own rule. This structure helps readers inspect each part without having to deduce the entire precedence order themselves.

Do not nest parentheses too deeply if intermediate conditions can be named in Java or precomputed Boolean properties can be provided on the root object. Parentheses should clarify logic; too many nesting levels can make an expression hard to follow.

## 6. Example Running an Expression in Java

An expression can be parsed once and then evaluated with an EvaluationContext:

    public class User {
        private String role;
        private String department;
        private boolean active;
        private boolean suspended;

        // getters and setters
    }

    User user = new User();
    user.setRole("EDITOR");
    user.setDepartment("CONTENT");
    user.setActive(true);
    user.setSuspended(false);

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("user", user);

    ExpressionParser parser = new SpelExpressionParser();

    Expression accessRule = parser.parseExpression(
            "(#user.role == 'ADMIN' or " +
            "(#user.role == 'EDITOR' and " +
            "#user.department == 'CONTENT')) and " +
            "#user.active and not (#user.suspended)"
    );

    Boolean allowed = accessRule.getValue(context, Boolean.class);

With the sample data, the EDITOR in CONTENT branch is true, the user is active and not suspended, so the result is true.

When an expression is long, the string can be formatted across multiple lines in Java code to make the groups clearly visible. Line breaks and indentation only improve readability; it is the parentheses inside the expression string that determine the logical grouping.

## 7. Guarding Conditions When Data May Be Null

A group of conditions often accesses multiple properties on the same object. If the root object may be null, check for null before accessing subsequent properties:

    #user != null and
    (
        #user.active and
        (
            #user.role == 'ADMIN' or
            #user.role == 'EDITOR'
        )
    )

The AND operator in SpEL evaluates with short-circuiting: if the left-hand side is already false, the right-hand side does not need to be evaluated. Therefore, the `#user != null` condition can guard subsequent `#user.active` accesses in the same AND branch.

However, short-circuiting does not replace input data validation. If a property has a nullable Boolean type and can return null, decide explicitly whether null is treated as false, a data error, or needs separate handling. Do not let business meaning depend on an unexpected null value.

## 8. Organizing Long Expressions for Maintainability

When an expression has many groups, apply a few practical rules:

- **Each group represents one business concept:** for example user permissions, account status, or value conditions.
- **Use parentheses for every OR group inside an AND chain:** this clarifies the scope of the alternative branch.
- **Place parentheses around negated conditions:** write `not (A or B)` when negating an entire group.
- **Maintain consistent indentation:** each level of nested parentheses should have its own indentation level.
- **Name complex groups:** if a group needs multiple lines of explanation, consider precomputing it into a Boolean variable in Java and passing it into the context.
- **Avoid repeating conditions with side effects:** logical expressions should prioritize reading state; avoid calling methods that mutate data or perform unexpected operations.

Example using intermediate Boolean variables:

    context.setVariable("hasRequiredRole", hasRequiredRole);
    context.setVariable("accountAvailable", accountAvailable);
    context.setVariable("transactionAllowed", transactionAllowed);

    Boolean allowed = parser.parseExpression(
            "#hasRequiredRole and " +
            "#accountAvailable and " +
            "#transactionAllowed"
    ).getValue(context, Boolean.class);

This approach lets SpEL focus on combining conditions, while the computation logic for each group is tested and managed in Java.

## 9. Testing Logical Branches

A long expression needs to be tested by individual group and by edge cases. For the access permission example above, at minimum test:

| Case | Role | Active | Suspended | Result |
|---|---|---:|---:|---:|
| Valid administrator | ADMIN | true | false | true |
| Editor in right department | EDITOR / CONTENT | true | false | true |
| Editor in wrong department | EDITOR / SALES | true | false | false |
| Inactive user | EDITOR / CONTENT | false | false | false |
| Suspended user | ADMIN | true | true | false |

In addition to normal true/false cases, test null values if the model permits null, and test each OR branch to ensure a true branch does not accidentally bypass a mandatory outer condition.

When the result is not as expected, reduce the expression into individual groups and evaluate them separately. Small Expressions can be created for each group, or Boolean variables can be computed in Java to compare against the result of the overall expression.

## 10. Key Takeaways

Parentheses clearly define the combination scope of `and`, `or`, and `not` in SpEL. `and` has higher precedence than `or`, so place parentheses around OR branches when they lie within an AND chain. For multi-part negated conditions, use `not (A or B)` to express the exact negation scope. Splitting expressions into groups by business meaning, guarding access to nullable properties, and testing each branch make long conditions easier to understand and more reliable.
