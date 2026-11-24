# AND, OR, and NOT in SpEL

The logical operators AND, OR, and NOT allow combining multiple conditions into a single boolean expression in Spring Expression Language (SpEL). They are commonly used to check state, determine permissions, or decide whether a configuration rule is satisfied.

SpEL supports both the readable keyword forms `and`, `or`, `not` and the short symbol forms `&&`, `||`, `!`. To write correct and maintainable expressions, it is necessary to understand truth tables, operator precedence, grouping with parentheses, and short-circuit behavior when evaluating the right-hand side.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Use `and`, `or`, `not` and their corresponding symbol forms.
- Determine the result of a logical expression using a truth table.
- Understand the precedence order among NOT, AND, and OR.
- Use parentheses to clearly express mandatory conditions and alternative conditions.
- Explain short-circuiting and how it affects evaluation of the right-hand side.
- Check for null before accessing nested properties.
- Combine logical operators with variables, properties, collections, and business conditions.
- Write tests for both true and false branches as well as edge cases.

You should know how to parse a SpEL expression, pass variables through EvaluationContext, and read a boolean value from Expression.

## 2. Three Basic Logical Operators

SpEL has three main logical operations:

| Meaning | Keyword form | Symbol form |
|---|---|---|
| AND — and | and | && |
| OR — or | or | \|\| |
| NOT — negation | not | ! |

Both forms in each row have the same logical meaning. The keyword form is often easier to read in configuration expressions; the symbol form is familiar to those who already know Java. A consistent style should be chosen within the same project.

### 2.1. AND — all conditions must be true

AND returns true only when both operands are true.

~~~text
#active and #verified
~~~

This condition requires the account to be both active and verified.

Truth table:

| A | B | A and B |
|---|---|---|
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

Use AND when each condition is a mandatory requirement. For example, an order is processed only when it has been paid and has not been cancelled:

~~~text
#order.paid and not #order.cancelled
~~~

### 2.2. OR — at least one condition must be true

OR returns true when at least one operand is true. It returns false only when both are false.

~~~text
#isAdmin or #isOwner
~~~

This condition allows access if the user is an admin or the resource owner.

Truth table:

| A | B | A or B |
|---|---|---|
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

Use OR when branches are alternatives. For example, an order is prioritized if it belongs to the VIP group or has a total exceeding the threshold:

~~~text
#customer.vip or #order.total >= #priorityThreshold
~~~

### 2.3. NOT — invert a boolean value

NOT turns true into false and false into true.

~~~text
not #disabled
~~~

Equivalent symbol form:

~~~text
!#disabled
~~~

NOT is a unary operator, meaning it applies only to a single expression following it. When negating a complex condition, place that condition in parentheses:

~~~text
not (#blocked or #expired)
~~~

The expression above is true only when both blocked and expired are false.

## 3. Combining Multiple Operators and Precedence

When an expression has multiple logical operators, SpEL applies the precedence order:

1. NOT is processed first.
2. AND is processed after NOT.
3. OR is processed after AND.

Comparison operations such as ==, !=, >, >=, <, and <= are grouped before being combined with logical operators.

Example:

~~~text
#age >= 18 and #verified or #isAdmin
~~~

Is interpreted as follows:

~~~text
((#age >= 18) and #verified) or #isAdmin
~~~

Because AND has higher precedence than OR, the expression is true if the user is of age and verified, or the user is an admin.

If the business rule requires verification in all cases, while age or admin permission are two alternatives, write:

~~~text
(#age >= 18 or #isAdmin) and #verified
~~~

The two expressions are not equivalent. With age = 16, verified = false, and isAdmin = true, the first expression returns true; the second expression returns false.

### 3.1. Parentheses for Grouping Conditions

Parentheses clarify the scope of a logical group and can change the result according to business intent.

Example:

~~~text
#enabled and (#role == 'ADMIN' or #role == 'MANAGER')
~~~

The user must be enabled and have one of the two roles. If the parentheses are omitted:

~~~text
#enabled and #role == 'ADMIN' or #role == 'MANAGER'
~~~

Because AND has higher precedence than OR, the expression will be equivalent to:

~~~text
(#enabled and #role == 'ADMIN') or #role == 'MANAGER'
~~~

In that case, MANAGER can satisfy the condition even when enabled is false. This is often a hard-to-spot logic bug if the expression is written on a single long line.

### 3.2. Negating a Group of Conditions

De Morgan's laws help transform logical expressions:

- NOT (A AND B) is equivalent to NOT A OR NOT B.
- NOT (A OR B) is equivalent to NOT A AND NOT B.

Example:

~~~text
not (#paid and #confirmed)
~~~

Equivalent to:

~~~text
not #paid or not #confirmed
~~~

And:

~~~text
not (#blocked or #expired)
~~~

Equivalent to:

~~~text
not #blocked and not #expired
~~~

When using these rules, keep parentheses around the negated group. This helps readers verify the exact scope of NOT.

## 4. Short-circuit: the Right-Hand Side May Be Skipped

AND and OR evaluate from left to right and can stop as soon as the result is determined. This is short-circuit behavior.

- With AND, if the left-hand side is false, the entire expression is definitely false; the right-hand side does not need to be evaluated.
- With OR, if the left-hand side is true, the entire expression is definitely true; the right-hand side does not need to be evaluated.

Example:

~~~text
#customer != null and #customer.active
~~~

If customer is null, the left-hand side is false so the right-hand side is not evaluated. As a result, the expression avoids accessing active on a null object.

An OR example:

~~~text
#isAdmin or #account.owner
~~~

If isAdmin is true, SpEL does not need to evaluate the right-hand side to determine the result. However, this example is only appropriate when the root object and the owner property are clearly designed.

### 4.1. Order of Left-Hand Side and Right-Hand Side Matters

Place the guard condition on the left:

~~~text
#order != null and #order.total > 0
~~~

This checks that order exists before reading total.

Avoid writing in the reverse order:

~~~text
#order.total > 0 and #order != null
~~~

The left-hand side may fail before the null check is performed.

### 4.2. Do Not Rely on the Right-Hand Side for Side Effects

Because short-circuiting can skip the right-hand side, do not place a mandatory action in a method call there:

~~~text
#enabled and #service.updateStatus()
~~~

If enabled is false, updateStatus may not be called. If enabled is true, the expression may alter state while checking a condition.

Actions should be performed in Java in a clear flow, followed by evaluating read-only conditions. A logical expression should describe a condition and return a predictable result.

## 5. Using Variables in EvaluationContext

SpEL variables have the # prefix. The application registers variables in the context before evaluation:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#age >= 18 and #verified and not #blocked");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("age", 21);
context.setVariable("verified", true);
context.setVariable("blocked", false);

Boolean allowed =
    expression.getValue(context, Boolean.class);
~~~

The result is true.

Variable values can be changed for another evaluation:

~~~java
context.setVariable("blocked", true);
Boolean allowedAgain =
    expression.getValue(context, Boolean.class);
~~~

The result this time is false.

Passing data into the context separates rules from data. User data should not be concatenated directly into the expression string, as doing so easily causes escaping errors and can cause input to be interpreted as SpEL syntax.

## 6. Combining Logic with Properties and Collections

### 6.1. Checking Nested Properties

For objects with multiple levels of properties, check intermediate objects before accessing further:

~~~text
#customer != null and #customer.address != null and #customer.address.city == 'Hanoi'
~~~

Because AND short-circuits, if customer is null then the subsequent parts are not evaluated. If customer exists but address is null, the third condition is skipped.

Safe navigation can be used:

~~~text
#customer?.address?.city == 'Hanoi'
~~~

This syntax is shorter, but you need to understand the null result when a path does not exist and how comparison operators handle that value. For critical rules, choose the style that clearly expresses the null policy.

### 6.2. Filtering Collections with Predicates

The selection operator uses `.?[...]` to filter elements. Inside the predicate, AND, OR, and NOT can be combined:

~~~text
#orders.?[active and total >= 100]
~~~

For example, filtering orders that are active and have a total of at least 100.

Another condition:

~~~text
#orders.?[(priority == 'HIGH' or customer.vip) and not cancelled]
~~~

Parentheses group the two priority alternatives before combining with the not-cancelled condition. Inside a predicate, #this represents the element currently being evaluated; property names without a prefix are resolved against the current element.

Keep predicates short. If a condition has many levels, many method calls, or needs to access services, move the filtering logic to Java for easier testing and optimization.

## 7. Combining with Conditional Expressions

The ternary conditional operator uses the syntax:

~~~text
condition ? valueIfTrue : valueIfFalse
~~~

Logic can be used to construct the condition:

~~~text
#active and #verified ? 'READY' : 'PENDING'
~~~

Example with multiple alternatives requiring clear grouping:

~~~text
(#isAdmin or #isOwner) and #resource.enabled
    ? 'ALLOW'
    : 'DENY'
~~~

The entire condition before `?` is evaluated before selecting a branch. Parentheses around the OR group show that both admin and owner must satisfy the resource.enabled condition.

## 8. Using Logical Operators in Spring

SpEL is used at many Spring integration points. In some contexts, expressions can read properties, beans, or information provided by the framework. Logical syntax still follows SpEL rules, but the root object and access permissions depend on where the expression is evaluated.

Example in the @Value annotation:

~~~java
@Value("#{ @featureFlags.enabled and @featureFlags.verified }")
private boolean featureReady;
~~~

In this configuration, Spring provides a bean resolver so the expression can reference a bean named featureFlags. The bean and corresponding properties must exist in the ApplicationContext.

Some annotations such as @PreAuthorize also use SpEL, but the Spring Security context provides its own variables and functions such as authentication or hasRole. Do not assume those names are available in a self-created StandardEvaluationContext. When using expressions in security annotations, verify the exact root object, role prefix, and permissions configured in the Security expression handler.

## 9. Data Types and Null Values

Logical operators require boolean-compatible results. Prefer passing an explicit Boolean rather than relying on unnecessary implicit conversions.

Cases that should be handled:

- Variable not registered in the context.
- Variable has a null value.
- Property does not exist.
- Property returns a type incompatible with a logical condition.
- Method called in the expression throws an exception.
- Collection or collection element is null.

Example of checking a variable for null before comparing:

~~~text
#score != null and #score >= 60
~~~

If score is null, the subsequent comparison is skipped thanks to short-circuiting. If data can be null, determine whether null means missing data, invalid, or requires a default value.

Elvis can provide a fallback value:

~~~text
(#score ?: 0) >= 60
~~~

Use a default value only when it accurately reflects the business rule. Replacing null with 0 can change the meaning of a condition if null truly represents an undetermined state.

## 10. Testing Logical Expressions

Start with the truth table of each operator:

| A | B | A AND B | A OR B |
|---|---|---|---|
| false | false | false | false |
| false | true | false | true |
| true | false | false | true |
| true | true | true | true |

NOT has two cases: NOT false is true and NOT true is false.

Then test the business groups:

| Case | Data | Expected result |
|---|---|---|
| All mandatory conditions true | active=true, verified=true | true |
| One AND condition false | active=true, verified=false | false |
| One OR branch true | isAdmin=true, isOwner=false | true |
| Both OR branches false | isAdmin=false, isOwner=false | false |
| NOT inverts true | blocked=true | false |
| Null object guarded | customer=null | false, customer.active is not accessed |
| OR group then AND | admin=true, enabled=false | false if enabled is a mandatory condition |

A short-circuit test can use a method that tracks how many times it is called in a test fixture. With the expression `false AND methodCall()` or `true OR methodCall()`, verify that the method on the right-hand side is not called. Only use a test method with no side effects other than a counter; do not use business side effects to control flow.

## 11. Common Errors and Diagnostics

| Symptom | Common cause | How to handle |
|---|---|---|
| OR condition returns true unexpectedly | AND has higher precedence than OR | Group the OR branch with parentheses |
| Accessing a null property causes an error | Null check placed after the access | Move the guard to the left-hand side or use safe navigation |
| NOT negates the wrong scope | Missing parentheses around the logic group | Write `not (A or B)` or `not (A and B)` |
| Expression returns a type error | Operand is not boolean-compatible | Check variable and property types |
| Right-hand side does not run | Short-circuit already determined the result | Check the left-hand value and condition order |
| Method runs inconsistently | Method is inside a branch that can be short-circuited | Do not place mandatory actions inside expressions |
| Long expression is hard to understand | Too many nested AND/OR groups | Add parentheses, use clear variable names, or move logic to Java |

When debugging, evaluate each condition individually to Boolean, then combine each group. Do not fix by adding parentheses randomly; rewrite the condition in business language and then translate each group into SpEL.

## 12. Practice Exercises

1. Write an expression requiring an account to be active and verified.
2. Write an expression allowing an admin or owner to access a resource.
3. Update the expression to require enabled in all cases, whether the user is an admin or an owner.
4. Use NOT to exclude blocked or expired accounts.
5. Use variables in EvaluationContext to evaluate age, verification, and status conditions.
6. Use short-circuiting to guard property access when an object may be null.
7. Filter an order list using selection, combining AND, OR, and NOT.
8. Write a test proving that the right-hand side is skipped when AND has a false left-hand side and OR has a true left-hand side.

## 13. Checklist for Using in Applications

- [ ] Have you chosen the keyword or symbol form and kept a consistent style?
- [ ] Do you understand the precedence of NOT, AND, and OR?
- [ ] Have you grouped OR branches and mandatory conditions with parentheses?
- [ ] Have you placed null guard conditions on the left-hand side?
- [ ] Do you understand that short-circuiting can skip the right-hand side?
- [ ] Are there any side-effect methods inside the expression?
- [ ] Do variables and properties have boolean-compatible types?
- [ ] Have you tested all true/false branches and null data?
- [ ] Have you identified the exact root object and variables of the Spring integration context?
- [ ] Is the expression short enough for others to maintain?

## 14. Conclusion

AND requires all conditions to be true, OR requires at least one condition to be true, and NOT inverts a boolean value. SpEL applies NOT before AND, then OR; parentheses help clearly express condition groups according to business rules. Short-circuiting allows skipping the right-hand side when the result is already determined, so place null guards on the left and avoid hiding actions with side effects in expressions. When using in Spring, always understand the root object and the permissions of EvaluationContext at the specific integration point.