# Precedence Between NOT, AND, and OR in Spring Expression Language (SpEL)

In Spring Expression Language (SpEL), the logical operators NOT, AND, and OR combine Boolean conditions into a larger expression. When an expression contains multiple operators, precedence determines which part is evaluated first and how conditions are grouped.

The core rules are: parentheses define explicit grouping, NOT operates on its operand, and AND has higher precedence than OR. Understanding this order accurately makes expressions easier to read, avoids unexpected results, and reduces bugs when implementing business rules.

## 1. Three Logical Operators in SpEL

SpEL supports three basic logical operations:

| Operator | Symbol form | Meaning |
|---|---|---|
| NOT | ! | Inverts a Boolean value: true becomes false and false becomes true. |
| AND | && | Result is true when both operands are true. |
| OR | \|\| | Result is true when at least one operand is true. |

In addition to symbols, SpEL allows writing operators using keywords:

| Keyword | Equivalent symbol |
|---|---|
| not | ! |
| and | && |
| or | \|\| |

Example:

~~~text
not enabled
!enabled

authenticated and active
authenticated && active

administrator or owner
administrator || owner
~~~

Within an expression, a single style should be used consistently so readers quickly recognize the logical structure. The examples in this article mainly use the keywords not, and, and or.

## 2. Truth Tables

A truth table describes the result of an operator for every possible combination of Boolean values.

### 2.1. NOT

NOT is a unary operator: it takes only one operand and inverts that value.

| A | NOT A |
|---|---|
| true | false |
| false | true |

Example:

~~~text
not locked
!locked
~~~

If locked is true then not locked returns false. If locked is false then the result is true.

### 2.2. AND

AND is true when both operands are true.

| A | B | A AND B |
|---|---|---|
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

Example:

~~~text
authenticated and hasPermission
~~~

The condition is true only when the user is authenticated and has the corresponding permission.

### 2.3. OR

OR is true when at least one of the two operands is true.

| A | B | A OR B |
|---|---|---|
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

Example:

~~~text
isAdministrator or isOwner
~~~

The condition is true when the user is an administrator or the resource owner. If both are false then the result is false.

## 3. Precedence Order of NOT, AND, and OR

When an expression has multiple logical operators, SpEL applies the following precedence order:

1. **Parentheses:** expressions inside parentheses are explicitly grouped and evaluated before the outer combination.
2. **NOT:** inverts the value of its operand.
3. **AND:** combines conditions together; takes precedence over OR.
4. **OR:** combines the remaining condition branches.

The logical order can be remembered as:

~~~text
NOT > AND > OR
~~~

Example:

~~~text
A or B and C
~~~

The expression is grouped as follows:

~~~text
A or (B and C)
~~~

AND is performed before OR. If you want OR to be performed first in a specific case, use parentheses:

~~~text
(A or B) and C
~~~

These two expressions can produce different results. With A=true, B=false, C=false:

- A or (B and C) returns true.
- (A or B) and C returns false.

Therefore, you should not read a long expression strictly from left to right while ignoring operator precedence.

## 4. Grouping Expressions with NOT, AND, and OR

NOT is the negation of a condition. When that condition is a comparison expression or consists of multiple parts, use parentheses to specify the exact part to negate.

For example, if you want to check that age does not meet the threshold of 18:

~~~text
not (age >= 18)
~~~

This clearly expresses that the entire comparison result of age >= 18 is negated. When combining comparison operators with NOT, parentheses help avoid ambiguity and clarify the intent of the expression.

Another example:

~~~text
not locked and enabled
~~~

According to precedence, the expression is equivalent to:

~~~text
(not locked) and enabled
~~~

NOT only inverts locked before the result is combined with enabled using AND.

For the expression:

~~~text
not locked and enabled or isAdministrator
~~~

The grouping according to precedence is:

~~~text
((not locked) and enabled) or isAdministrator
~~~

If the business requirement is to allow only administrators or people who are both unlocked and enabled, it can be written more clearly:

~~~text
isAdministrator or (not locked and enabled)
~~~

If the requirement is that everyone must not be locked, while administrators are allowed to bypass the enabled condition, the expression above also expresses that structure. Choose the grouping according to the business meaning and then use parentheses to encode that meaning.

## 5. Parentheses Help Express Intent

Parentheses serve to group part of an expression into a logical unit. They are especially useful when there are multiple AND and OR branches.

Compare two ways of writing:

~~~text
authenticated and administrator or owner
~~~

and:

~~~text
authenticated and (administrator or owner)
~~~

The first way is grouped into:

~~~text
(authenticated and administrator) or owner
~~~

The second way requires being authenticated first, and then being an administrator or an owner.

Example with authenticated=false, administrator=false, owner=true:

- The first way returns true because the owner branch is true.
- The second way returns false because authenticated is false.

Another pair of expressions:

~~~text
not disabled and active or publicResource
~~~

~~~text
not disabled and (active or publicResource)
~~~

In the first expression, publicResource=true can make the entire expression true even if the resource is disabled. In the latter expression, disabled=true makes the condition not disabled false and the entire AND false.

When a rule has many conditions, place parentheses around each business group such as status, access rights, ownership, or exceptions. This grouping makes expressions easier to review and easier to change.

## 6. Example in SpEL with a Root Object

Suppose an application has a resource access rule. A user is allowed access when authenticated and belonging to one of the cases: being an administrator, or being an editor who owns the resource.

~~~java
public class AccessPolicy {
    private final boolean authenticated;
    private final boolean administrator;
    private final boolean editor;
    private final boolean owner;

    public AccessPolicy(
            boolean authenticated,
            boolean administrator,
            boolean editor,
            boolean owner) {
        this.authenticated = authenticated;
        this.administrator = administrator;
        this.editor = editor;
        this.owner = owner;
    }

    public boolean isAuthenticated() {
        return authenticated;
    }

    public boolean isAdministrator() {
        return administrator;
    }

    public boolean isEditor() {
        return editor;
    }

    public boolean isOwner() {
        return owner;
    }
}
~~~

Create the expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "authenticated and (administrator or (editor and owner))"
);
~~~

Evaluate the expression with data:

~~~java
AccessPolicy policy = new AccessPolicy(
        true,   // authenticated
        false,  // administrator
        true,   // editor
        true    // owner
);

Boolean allowed = expression.getValue(policy, Boolean.class);

// allowed == true
~~~

The grouping of the expression shows:

1. The user must be authenticated.
2. Then the user can be an administrator.
3. If not an administrator, the user needs to be both an editor and an owner.

If owner is replaced with false in the example, the editor and owner branch becomes false. Because administrator is also false, the parenthesized part is false and the final result is false.

If authenticated=false, the entire AND expression is also false even if the subsequent permission conditions are true.

## 7. Example with NOT and Multiple OR Branches

Suppose a feature is enabled only when the account is not locked and the user belongs to one of the allowed groups:

~~~text
not accountLocked and (isAdministrator or isSupport or isOwner)
~~~

The structure can be read as:

- The account must not be locked.
- The user is an administrator, support staff, or owner.

Without parentheses:

~~~text
not accountLocked and isAdministrator or isSupport or isOwner
~~~

then AND is performed before OR. The expression is equivalent to:

~~~text
((not accountLocked) and isAdministrator) or isSupport or isOwner
~~~

In that case isSupport=true or isOwner=true can make the result true even when accountLocked=true. If this violates the business requirement, the OR branches must be grouped with parentheses as in the first example.

## 8. Step-by-Step Evaluation and Short-Circuiting

AND and OR in logical expressions have short-circuit evaluation behavior:

- With AND, if the left-hand operand is false then the result is definitely false. SpEL does not need to evaluate the right-hand operand.
- With OR, if the left-hand operand is true then the result is definitely true. SpEL does not need to evaluate the right-hand operand.
- Only when the result cannot yet be determined from the left-hand operand is the right-hand operand evaluated.

Example:

~~~text
hasProfile and profile.enabled
~~~

If hasProfile=false, the profile.enabled part does not need to be evaluated. This is useful when the right-hand side depends on data that is only valid when the condition on the left-hand side is true.

Another example:

~~~text
isAdministrator or user.hasSpecialAccess()
~~~

If isAdministrator=true, SpEL can determine the OR result immediately without calling the method on the right-hand side.

Short-circuiting does not replace safe expression design. Arrange guard conditions before parts that may access null data or perform method calls.

## 9. Null Boolean Values and Safe Conditions

Logical operators require Boolean operands. If a Boolean property can take null, do not assume null is equivalent to false.

For example, with an enabled property of type java.lang.Boolean, the expression:

~~~text
not enabled
~~~

may fail to evaluate when enabled is null, because there is no Boolean value to invert.

The value can be checked explicitly:

~~~text
enabled == true
enabled == false
enabled != null and enabled
~~~

enabled == true is true only when enabled is actually Boolean true. The expression enabled != null and enabled takes advantage of short-circuiting: if enabled is null, the left-hand side is false and the right-hand side is not evaluated.

For nullable Boolean properties, explicit comparisons make expressions easier to understand and avoid assumptions about data.

## 10. Combining Comparison Operators with NOT, AND, and OR

In business conditions, logical operators are often combined with numeric, string, or status comparisons.

Example:

~~~text
age >= 18 and accountActive
~~~

~~~text
status == 'APPROVED' or isAdministrator
~~~

~~~text
not (balance < 0) and accountActive
~~~

~~~text
(isPremium or isStaff) and not suspended
~~~

Comparisons produce Boolean results, and then NOT, AND, or OR combine those results. When there are multiple comparisons and logical branches, use parentheses to express condition groups according to the exact requirement.

An expression can parse successfully yet still fail to evaluate if a property does not exist, a data type is incompatible, or a method to be called is not accessible. Check the root object and EvaluationContext when encountering errors.

## 11. Common Mistakes

| Mistake | Why it is a problem | How to fix |
|---|---|---|
| Assuming OR takes precedence over AND | AND has higher precedence than OR. | Add parentheses around the OR group if needed. |
| Writing a long expression without grouping | Readers find it hard to recognize the scope of each condition. | Use parentheses according to each business group. |
| Negating the wrong scope with NOT | NOT only operates on its operand. | Place parentheses around the condition to be negated. |
| Treating null as false | null is not a Boolean value. | Check for null or compare with true/false. |
| Comparing Boolean with the string 'true' | String and Boolean are two different types. | Use the literal true or false. |
| Using arbitrary uppercase keywords | Expression syntax requires proper operator tokens. | Consistently use not, and, or or the corresponding symbols. |
| Relying on left-to-right order | Operator precedence determines how things are grouped. | Analyze according to NOT, AND, OR and add parentheses. |
| Using a right-hand side that can fail without a guard condition | The right-hand side may be evaluated before necessary conditions are met. | Place the guard condition on the left-hand side of AND or regroup. |

## 12. Testing Expressions During Development

You can parse an expression first and then evaluate it with multiple datasets to confirm the results:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "authenticated and (administrator or (editor and owner))"
);

Boolean first = expression.getValue(
        new AccessPolicy(true, false, true, true),
        Boolean.class
);

Boolean second = expression.getValue(
        new AccessPolicy(true, false, true, false),
        Boolean.class
);

Boolean third = expression.getValue(
        new AccessPolicy(false, true, true, true),
        Boolean.class
);

// first == true
// second == false
// third == false
~~~

Test cases should include:

- All component conditions are false.
- Only one OR branch is true.
- One AND branch is missing one condition.
- A NOT condition flips from false to true and vice versa.
- Nullable Boolean values if the data model allows null.
- Combinations with parentheses that change the result.

When troubleshooting, distinguish syntax parsing errors (ParseException) from evaluation errors (EvaluationException). Check the expression, property data types, root object, and components in the EvaluationContext.

## 13. Key Takeaways

- NOT inverts a Boolean value; AND requires both sides to be true; OR requires only one side to be true.
- Operators can be written with keywords not, and, or or symbols !, &&, ||.
- Logical precedence is NOT before AND, and AND before OR.
- Parentheses help group conditions and override the default combination order.
- When combining comparisons with NOT, place parentheses around the comparison to be negated.
- AND and OR can short-circuit; place guard conditions before expressions that depend on data.
- Nullable Booleans must be handled explicitly, not automatically treated as false.
- Writing expressions by business groups makes them easier to read, test, and maintain.
