# Testing Truth Tables of Logical Expressions in SpEL

## 1. Role of Logical Operators

Spring Expression Language (SpEL) supports Boolean expressions to combine multiple conditions into a single result. Logical operators are commonly used after a comparison, when checking an object's state, or when expressing business rules such as access permissions, activation conditions, and valid states.

SpEL has three logical operators:

| Meaning | Keyword form | Symbol form | Number of operands |
|---|---|---|---:|
| AND — and | `and` | `&&` | 2 |
| OR — or | `or` | `||` | 2 |
| NOT — negation | `not` | `!` | 1 |

The keyword form and symbol form have the same meaning. The keywords `and`, `or`, `not` are case-insensitive. For example, `true AND false` has the same result as `true and false`.

The AND and OR operators are binary operators because they require two Boolean expressions. NOT is a unary operator because it negates only one Boolean expression.

## 2. Basic Truth Tables

A truth table lists the result of a logical expression for every possible combination of input values. With two Boolean variables A and B, there are four combinations: both true, only A true, only B true, and both false.

### 2.1. AND — both conditions must be true

The expression `A and B` returns `true` only when both A and B are `true`:

| A | B | A AND B |
|---|---|---|
| true | true | **true** |
| true | false | false |
| false | true | false |
| false | false | false |

AND can be read as a rule requiring simultaneous satisfaction: all conditions must be met.

Example:

```java
boolean result = parser.parseExpression("true and false")
        .getValue(Boolean.class);
// result == false
```

Equivalent symbol form:

```java
boolean result = parser.parseExpression("true && false")
        .getValue(Boolean.class);
// result == false
```

Common application: the user must be active **and** have administrator permissions to perform the operation.

```text
active and administrator
```

If either condition is false, the entire AND expression is false.

### 2.2. OR — at least one condition must be true

The expression `A or B` returns `true` when A is true, B is true, or both are true. It is false only when both A and B are false:

| A | B | A OR B |
|---|---|---|
| true | true | **true** |
| true | false | **true** |
| false | true | **true** |
| false | false | false |

OR in SpEL is inclusive OR, not XOR. Therefore, the case where both conditions are true still yields `true`.

Example:

```java
boolean result = parser.parseExpression("true or false")
        .getValue(Boolean.class);
// result == true
```

Equivalent symbol form:

```java
boolean result = parser.parseExpression("true || false")
        .getValue(Boolean.class);
// result == true
```

Common application: the user is allowed access if they are the owner **or** an administrator.

```text
owner or administrator
```

Only when both conditions are false is the OR result `false`.

### 2.3. NOT — invert a Boolean value

NOT takes only one operand and inverts its value:

| A | NOT A |
|---|---|
| true | false |
| false | true |

Example:

```java
boolean result = parser.parseExpression("!true")
        .getValue(Boolean.class);
// result == false
```

Equivalent keyword form:

```java
boolean result = parser.parseExpression("not true")
        .getValue(Boolean.class);
// result == false
```

NOT is useful when needing to express a negated condition, such as `not disabled` or `!blocked`. For complex expressions, place the operand in parentheses to clarify the negation scope: `not (A and B)`.

## 3. How to Construct and Verify a Truth Table Yourself

To verify a logical expression with multiple variables, list all input combinations and compute the result operator by operator.

With n independent Boolean variables, there are (2^n) combinations to test. Example:

- 1 variable: 2 combinations.
- 2 variables: 4 combinations.
- 3 variables: 8 combinations.
- 4 variables: 16 combinations.

Consider the expression:

```text
(A and B) or not C
```

Evaluate in order:

1. Compute `A and B`.
2. Compute `not C`.
3. Take the results of the two steps above to compute OR.

Full truth table:

| A | B | C | A AND B | NOT C | (A AND B) OR NOT C |
|---|---|---|---|---|---|
| false | false | false | false | true | **true** |
| false | false | true | false | false | false |
| false | true | false | false | true | **true** |
| false | true | true | false | false | false |
| true | false | false | false | true | **true** |
| true | false | true | false | false | false |
| true | true | false | true | true | **true** |
| true | true | true | true | false | **true** |

The final result is false only when C is true while A and B are not both true. When A and B are both true, the expression is always true regardless of C.

## 4. Evaluating Expressions Using Java

`SpelExpressionParser` can be used to test an expression directly without needing a root object:

```java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class LogicExpressionExample {
    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();

        boolean andResult = parser.parseExpression(
                "true and false").getValue(Boolean.class);

        boolean orResult = parser.parseExpression(
                "true or false").getValue(Boolean.class);

        boolean notResult = parser.parseExpression(
                "not false").getValue(Boolean.class);

        System.out.println(andResult); // false
        System.out.println(orResult);  // true
        System.out.println(notResult); // true
    }
}
```

To test all four cases of AND and OR, expressions can be constructed from input values:

```java
ExpressionParser parser = new SpelExpressionParser();

boolean[] values = {false, true};

for (boolean a : values) {
    for (boolean b : values) {
        String andExpression = a + " and " + b;
        String orExpression = a + " or " + b;

        Boolean andResult = parser.parseExpression(andExpression)
                .getValue(Boolean.class);
        Boolean orResult = parser.parseExpression(orExpression)
                .getValue(Boolean.class);

        System.out.printf(
                "A=%s, B=%s, AND=%s, OR=%s%n",
                a, b, andResult, orResult);
    }
}
```

The loop generates all four combinations of two variables. The printed output can be compared directly against the truth tables in the previous section.

## 5. Combining Logical Operators with Comparisons

In applications, operands of AND/OR/NOT are usually comparison expressions rather than literals `true` or `false`.

For example, an order is approved only when the total meets the threshold and the status is `READY`:

```text
total >= 100000 and status == 'READY'
```

For example, an account is allowed to act if it is an administrator or the resource owner:

```text
administrator or owner
```

For example, the account is not locked and email is verified:

```text
not locked and emailVerified
```

Comparisons such as `==`, `!=`, `>`, `>=`, `<`, `<=` produce Boolean results, which can be used directly as logical operands. Property expressions such as `active` can also be used directly if the read value is Boolean or convertible to Boolean.

### 5.1. Evaluating with a Root Object

Suppose the application has a user class:

```java
public class User {
    private int age;
    private boolean active;
    private boolean administrator;

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }

    public boolean isAdministrator() {
        return administrator;
    }
}
```

The object can be set as the root object and then the expression evaluated:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context =
        new StandardEvaluationContext();

User user = loadUser();

Expression expression = parser.parseExpression(
        "age >= 18 and active and (administrator or age >= 21)");

Boolean allowed = expression.getValue(context, user, Boolean.class);
```

The expression requires the user to be at least 18 years old, active, and simultaneously an administrator or at least 21 years old. Using parentheses around the OR part helps clarify the condition group.

## 6. Grouping Order and Parentheses

When an expression has multiple operators, parentheses help readers determine the exact condition group to compute first. Use parentheses proactively rather than letting operator precedence rules become a hard-to-spot assumption.

Example:

```text
(active and verified) or administrator
```

This expression means the user is accepted if they are both active and verified, or if they are an administrator.

Whereas:

```text
active and (verified or administrator)
```

This expression requires the user to be active; after that, they only need to be verified or an administrator.

The two expressions are not equivalent:

| active | verified | administrator | (active AND verified) OR administrator | active AND (verified OR administrator) |
|---|---|---|---|---|
| false | false | false | false | false |
| false | false | true | true | false |
| false | true | false | false | false |
| false | true | true | true | false |
| true | false | false | false | false |
| true | false | true | true | true |
| true | true | false | true | true |
| true | true | true | true | true |

The clearest difference appears when `administrator = true` while `active = false`: the first expression allows, whereas the second expression rejects.

## 7. Useful Logical Laws

Boolean algebra laws help simplify or verify expressions.

### 7.1. Identity Laws

```text
A and true  = A
A or false  = A
```

AND with `true` and OR with `false` preserve the original value.

### 7.2. Domination Laws

```text
A and false = false
A or true   = true
```

AND with `false` is always false; OR with `true` is always true.

### 7.3. Double Negation Law

```text
not (not A) = A
```

Negating twice restores the original value.

### 7.4. De Morgan's Laws

```text
not (A and B) = (not A) or (not B)
not (A or B)  = (not A) and (not B)
```

For example, negating the statement "the user is active and verified" is equivalent to "the user is inactive or not verified":

```text
not (active and verified)
```

is equivalent to:

```text
not active or not verified
```

These laws can be used to detect errors when translating a business condition into a SpEL expression.

## 8. Short-Circuiting: Skipping Unnecessary Operands

SpEL evaluates AND and OR using a short-circuit mechanism:

- With `A and B`, if A is `false`, SpEL already knows the final result is `false`, so it does not need to evaluate B.
- With `A or B`, if A is `true`, SpEL already knows the final result is `true`, so it does not need to evaluate B.

Example:

```text
false and checkPermission()
true or loadFallback()
```

In the first expression, `checkPermission()` is not called. In the second expression, `loadFallback()` is not called.

Short-circuiting has practical significance when the right-hand operand can be costly, data-dependent, or have side effects. Because the right-hand operand can be skipped, do not put operations that must run in that position. Arrange conditions to perform simple and safe checks before performing costly operations.

For example, check a reference before reading a nested property:

```text
user != null and user.active
```

If `user != null` is `false`, the `user.active` part is not evaluated. This is a way to guard the expression against accessing a property on a null root object in this case.

Short-circuiting does not change the truth table; it only changes whether the right-hand operand needs to be evaluated.

## 9. Boolean, null, and Data Type Errors

Logical operators require operands that can be evaluated to Boolean. For ordinary Boolean expressions, use `true` and `false` literals without quotes:

```text
true and false
```

Do not confuse them with strings:

```text
'true' and 'false'
```

The two quoted values are String literals, not Boolean literals. SpEL may apply type conversion mechanisms in some cases, but you should not rely on implicit conversion to write clear logical conditions.

An operand with value `null` is not a third Boolean value in a truth table. When SpEL cannot convert that value to Boolean, evaluation can throw `SpelEvaluationException` due to a type conversion error. Therefore, do not apply a two-valued truth table directly to null data as if null were synonymous with false.

For example, if `user` can be null, check before accessing properties:

```text
user != null and user.active
```

If a Boolean property can contain null (for example `Boolean` instead of `boolean`), handle null explicitly before using that property as an operand:

```text
enabled != null and enabled
```

When checking for null, use the comparison operators `== null` or `!= null`; do not write `not null` as a substitute for checking a null value.

## 10. Common Errors

| Error or unexpected result | Cause | How to handle |
|---|---|---|
| AND returns false even though one condition is true | AND requires both conditions to be true. | Check each operand against the AND truth table. |
| OR returns true when both conditions are true | OR is inclusive OR, not XOR. | If mutual exclusion is needed, write an XOR expression using AND/OR/NOT combinations. |
| NOT negates a different part of the expression than intended | Operand scope is unclear. | Use parentheses, for example `not (A and B)`. |
| Writing `&` or `|` does not work as expected | SpEL's symbol forms are `&&` and `||`. | Use the proper two-character operators or keyword forms. |
| String `'true'` does not behave like Boolean | Quoted values are Strings. | Use `true`/`false` literals or convert types explicitly. |
| Evaluation fails when a property is null | Logical operand lacks a valid Boolean value. | Check for null first with `!= null`. |
| Calling a method on the right-hand side does not execute | Short-circuit already determined the result from the left-hand operand. | Do not place mandatory side effects in an operand that can be skipped. |
| Long expression is hard to read or wrongly grouped | Condition groups are not expressed with parentheses. | Split into parenthesized groups and check the truth table. |
| Comparison yields a different result than expected | Value or type of an operand is not as anticipated. | Check runtime values, comparisons, and data types before combining logic. |

## 11. Workflow for Verifying a Logical Expression

When given a business expression to verify, you can follow this workflow:

1. Identify all Boolean variables or comparisons that produce Booleans.
2. Add parentheses to clearly express condition groups.
3. List all input combinations; with n variables, use (2^n) rows.
4. Compute NOT first on its corresponding operand, then compute AND/OR groups according to the expression structure.
5. Cross-check results against the business meaning using true, false, and edge cases.
6. Also test null cases or mismatched data types because these cases can cause evaluation errors rather than producing true/false results.
7. Re-run the expression using `SpelExpressionParser` with a context and root object matching the application environment.

Truth tables help prove the logic for Boolean inputs. Testing in SpEL must also account for how properties, methods, converters, and EvaluationContext supply values for operands.

## 12. Key Takeaways

- SpEL has AND (`and`/`&&`), OR (`or`/`||`), and NOT (`not`/`!`).
- AND is true only when both operands are true; OR is true when at least one operand is true; NOT inverts the value.
- OR is inclusive OR: both operands being true still yields true.
- With n Boolean variables, the truth table has (2^n) combinations.
- Use parentheses to express condition groups and avoid misinterpreting expression meaning.
- AND/OR have short-circuiting: the right-hand operand may not be evaluated.
- Operands must return valid Boolean values; null and wrong data types can cause conversion errors.
- Use truth tables to verify logic and use the SpEL parser to verify actual evaluation behavior.

## References

- [Spring Framework Reference — Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [SpEL OpAnd Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/OpAnd.html)
- [SpEL OpOr Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/OpOr.html)
