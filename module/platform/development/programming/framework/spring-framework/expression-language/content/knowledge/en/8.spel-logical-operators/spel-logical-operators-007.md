# Avoiding Duplicate Conditions and Hard-to-Read Negations

In Spring Expression Language (SpEL), logical operators allow combining multiple conditions into a single expression. As business rules grow, expressions easily develop repeated condition segments, multiple negation marks, or logical branches that are difficult to verify.

A readable expression needs to make clear which conditions must be true, which conditions are allowed to be false, and why a case is rejected. This can be improved by grouping conditions, naming shared rules, leveraging short-circuit evaluation, and writing conditions in affirmative form.

## 1. Logical Operators in SpEL

SpEL provides three basic logical operations:

| Symbol | Equivalent keyword | Meaning |
|---|---|---|
| **&&** | **and** | AND: both sides must be true |
| **\|\|** | **or** | OR: at least one side is true |
| **!** | **not** | NOT: inverts the Boolean value |

Example:

~~~java
order.total > 100 && order.status == 'PAID'
~~~

The condition is true when the total is greater than 100 and the status is PAID.

Example using OR:

~~~java
order.status == 'PAID' || order.status == 'SETTLED'
~~~

The condition is true when the order is in one of the two statuses.

Example using NOT:

~~~java
!order.cancelled
~~~

The condition is true when cancelled is false.

SpEL supports both symbols and keywords. Within a project, choose one consistent style. Symbols are concise, while keywords can be easier to read in some business expressions. Whichever you choose, use parentheses when combining multiple condition groups.

## 2. Short-Circuit Evaluation

An important characteristic of AND and OR is that SpEL performs short-circuit evaluation:

- With AND, if the left-hand side is false, the right-hand side does not need to be evaluated.
- With OR, if the left-hand side is true, the right-hand side does not need to be evaluated.

### 2.1. Using AND to Guard Property Access

Suppose customer may be null:

~~~java
order.customer != null && order.customer.active
~~~

If customer is null, the first side is false and SpEL skips the second side. Because of that, the expression does not attempt to access active on a null customer.

Multi-level checks can be continued:

~~~java
order.customer != null
    && order.customer.profile != null
    && order.customer.profile.verified
~~~

Each step is evaluated only if all preceding conditions are true.

The order of the sides therefore matters. Place the null check before the access that depends on that object.

### 2.2. Using OR to Provide a Fallback Branch

~~~java
order.customer == null || order.customer.active
~~~

If customer is null, the first side is true so the second side is skipped. The expression returns true.

However, check whether this interpretation matches the business rule. The expression above treats the case with no customer as an acceptable condition. If the business rule requires customer to necessarily exist, use AND with a null check instead of OR.

### 2.3. Do Not Rely on Side Effects in Skipped Branches

Because a side may not be evaluated, do not use method calls with side effects to update state, write data, or send notifications inside logical conditions.

A conditional expression should read data and return a deterministic result. If an action needs to be performed, handle that action in the Java layer after evaluating the condition.

## 3. Avoiding Repeating the Same Condition

### 3.1. Recognizing Repeated Conditions

An expression may repeat the same check across multiple branches:

~~~java
(order.customer != null && order.customer.active && order.total > 0)
||
(order.customer != null && order.customer.active && order.priority)
~~~

Both branches require customer to exist and be active. The shared condition part can be factored out:

~~~java
order.customer != null
    && order.customer.active
    && (order.total > 0 || order.priority)
~~~

The new expression makes it clear: customer must exist and be active; then the order must have a positive total or be marked as priority.

This grouping is logically equivalent because the shared condition part must be true in both branches. Parentheses clarify the two alternatives afterward.

### 3.2. Naming Shared Conditions

When a condition is used in multiple expressions or has its own business meaning, name it in the Java layer.

For example, the model provides a meaningful property:

~~~java
order.eligibleForProcessing
~~~

Instead of repeating:

~~~java
order.customer != null
    && order.customer.active
    && order.payment != null
    && order.payment.confirmed
~~~

A clearly named property or method helps readers understand the business purpose without having to analyze all the implementation details.

Names should describe state or outcome, such as:

- **eligibleForProcessing**
- **paymentConfirmed**
- **customerActive**
- **withinCreditLimit**

Avoid generic names such as **check1**, **flag2**, or **conditionA**.

### 3.3. Using Variables in EvaluationContext

If the application needs to reuse an already computed result, a variable can be placed into EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("customerActive", customerIsActive);
context.setVariable("withinCreditLimit", withinCreditLimit);
~~~

The expression can use the variables:

~~~java
#customerActive && #withinCreditLimit
~~~

SpEL variables are referenced with the **#** sign. Variable values are supplied from Java before evaluation.

This approach is suitable when:

- An expensive check has already been computed in the Java layer.
- Multiple expressions share the same result.
- You want to separate data retrieval from rule expression.
- You need explicit control over the data passed into the expression.

Manage the lifecycle of the context and variables per request or evaluation. Do not share a context with mutable variables across processing threads without an appropriate synchronization mechanism.

### 3.4. Using Methods with Clear Names

Methods can be called on the root object or a policy object passed into the context:

~~~java
order.isEligibleForProcessing()
~~~

or:

~~~java
#policy.canProcess(order)
~~~

Example:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("policy", processingPolicy);

Boolean allowed = parser
        .parseExpression("#policy.canProcess(#root)")
        .getValue(context, Boolean.class);
~~~

Methods should focus on one clearly named business rule. Keep methods pure or at least free of side effects, so expression results are predictable and independently testable.

Do not put an overly general method into the context and then create expressions calling the method with many complex arguments. If a rule requires multiple processing steps, move that part to Java.

## 4. Avoiding Multi-Level Negations

### 4.1. Recognizing Double Negatives

Expressions with multiple layers of negation are often hard to understand:

~~~java
!(!order.active)
~~~

This expression is equivalent to:

~~~java
order.active
~~~

Similarly, a property name that already carries a negative meaning and is negated again:

~~~java
!order.notAllowed
~~~

Readers have to process two negations to understand the result. If possible, rename the property or use an affirmative condition:

~~~java
order.allowed
~~~

Property names should describe positive and clear states. For example, prefer **enabled**, **verified**, **eligible**, or **allowed** when they accurately reflect the domain.

### 4.2. Using Direct Negation and Parentheses

If a single condition needs to be negated:

~~~java
!order.cancelled
~~~

If an entire group of conditions needs to be negated, wrap the group in parentheses:

~~~java
!(order.status == 'PAID' || order.status == 'SETTLED')
~~~

Parentheses indicate that NOT applies to the entire inner expression. If parentheses are omitted or misplaced, the logical meaning can change.

### 4.3. Preferring Affirmative Conditions

Compare two ways:

~~~java
!order.blocked && !order.suspended
~~~

and:

~~~java
order.active
~~~

If the domain defines the active state precisely as neither blocked nor suspended, the **active** property is easier to read.

However, merge conditions only when the business meaning is truly equivalent. If active also depends on expiration date, payment status, or user permissions, ensure the composite property fully reflects those rules.

Do not create an affirmative property solely to make an expression shorter if it hides several distinct conditions.

## 5. Transforming Conditions with De Morgan's Laws

De Morgan's laws help transform the negation of an AND/OR group:

| Original expression | Equivalent expression |
|---|---|
| **!(A && B)** | **!A \|\| !B** |
| **!(A \|\| B)** | **!A && !B** |

Example:

~~~java
!(order.paid && order.shipped)
~~~

Equivalent to:

~~~java
!order.paid || !order.shipped
~~~

Meaning: not simultaneously satisfying both paid and shipped conditions. As long as one of the two conditions is false, the expression is true.

Second example:

~~~java
!(order.cancelled || order.expired)
~~~

Equivalent to:

~~~java
!order.cancelled && !order.expired
~~~

Meaning: the order is neither cancelled nor expired.

De Morgan's laws are useful when converting a negated condition into individual conditions. However, the transformed expression is not always easier to read. Choose the form that expresses the business statement most clearly and always keep parentheses when grouping conditions.

## 6. Combining Null Checks and Negation

Negated conditions often cause errors easily if a property can be null.

Example:

~~~java
!order.customer.active
~~~

If customer is null, accessing active may fail. Do not assume NOT handles null values automatically.

If the business rule requires customer to exist and not be active:

~~~java
order.customer != null && !order.customer.active
~~~

If the business rule treats a nonexistent customer as also being an inactive case:

~~~java
order.customer == null || !order.customer.active
~~~

These two expressions are not equivalent. Clarify the meaning of null before choosing which way to write it.

For a nullable Boolean wrapper, decide whether null means false, undetermined, or invalid data. It can be checked explicitly:

~~~java
order.confirmed == true
~~~

or:

~~~java
order.confirmed != null && order.confirmed
~~~

The second form clearly shows that the value must exist and must be true. If all three states—true, false, and null—need to be distinguished, keep the null check separate rather than forcing them into a single Boolean value.

## 7. Clarifying Condition Groups with Parentheses

When combining AND and OR, parentheses help readers see the boundaries of each group:

~~~java
(order.status == 'PAID' || order.status == 'SETTLED')
    && (order.total > 0 || order.priority)
~~~

Meaning:

- Status must be PAID or SETTLED.
- At the same time, the order must have a positive total or be marked as priority.

Do not write many conditions on one long line if they can be split across lines by business group. Consistent line breaks and indentation help detect missing parentheses and reduce the chance of misunderstanding evaluation order.

If an expression has too many nested groups, that is a sign that part of the logic should be moved to a named method or property.

## 8. Refactoring Example from a Hard-to-Read Expression

Suppose a rule allows processing an order when the customer is active, the order has not been cancelled, and one of two conditions is satisfied: already paid, or a priority order with a positive total.

Expression with duplication and multiple negations:

~~~java
(order.customer != null
    && order.customer.active
    && !order.cancelled
    && order.payment != null
    && order.payment.confirmed)
||
(order.customer != null
    && order.customer.active
    && !order.cancelled
    && order.priority
    && order.total > 0)
~~~

Shared conditions can be grouped:

~~~java
order.customer != null
    && order.customer.active
    && !order.cancelled
    && (
        (order.payment != null && order.payment.confirmed)
        || (order.priority && order.total > 0)
    )
~~~

The resulting expression has a clearer structure:

1. The customer must exist and be active.
2. The order is not cancelled.
3. The order is already paid or is a priority order with a positive total.

If this rule is used in multiple places, the shared condition part can be moved to a method:

~~~java
order.isEligibleForProcessing()
~~~

Then SpEL only expresses the combination with other conditions:

~~~java
order.isEligibleForProcessing() && request.channel == 'ONLINE'
~~~

Refactoring is not just about reducing character count. The goal is for each expression to express a business meaning that can be inspected and tested independently.

## 9. Workflow for Improving a Logical Expression

When encountering a long or hard-to-understand expression, you can proceed in this order:

1. **Separate atomic conditions.** Write out each check such as customer exists, status is valid, total is positive.
2. **Find duplicated parts.** Identify conditions appearing in multiple branches and check whether they can be factored out.
3. **Define the meaning of null.** Check which properties can be null and place guards before dependent accesses.
4. **Reduce negations.** Simplify double negatives, consider renaming properties, or use affirmative methods.
5. **Use parentheses.** Group conditions by business rule, especially when mixing AND and OR.
6. **Name shared rules.** Use properties, context variables, or methods if a condition is reused.
7. **Test edge cases.** Include null, true, false, and important state combinations.
8. **Re-evaluate readability.** Can someone else translate the expression into a business statement without having to reason through multiple layers?

Do not refactor merely by deleting textual duplication. Two conditions that look alike may differ in null handling, side effects, or the data being read. Group them only after confirming identical meaning and identical evaluation conditions.

## 10. Testing Logic and Short-Circuiting

Test both the Boolean value and whether branches are actually evaluated.

Example with pure expressions:

~~~java
ExpressionParser parser = new SpelExpressionParser();

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("false && true")
                .getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("true || false")
                .getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("!(false || false)")
                .getValue(Boolean.class)
);
~~~

For expressions with a null guard, test both cases:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Boolean allowed = parser
        .parseExpression(
                "order.customer != null && order.customer.active"
        )
        .getValue(context, Boolean.class);
~~~

Test when customer is null and when customer exists. The null case must yield the result matching the designed meaning, without triggering unexpected property access.

If possible, test the combination table for the business rule. For example, with two conditions A and B, test all four cases: true/true, true/false, false/true, and false/false. That helps catch logic transformation errors when grouping conditions or applying De Morgan's laws.

## 11. Common Design Mistakes

| Issue | Consequence | How to improve |
|---|---|---|
| Repeating the same condition in multiple branches | Hard to edit and easy for rules to drift between branches | Factor out shared conditions or name them as a property/method |
| Double negatives | Readers must invert meaning multiple times | Use affirmative conditions |
| Missing parentheses when mixing AND/OR | Hard to recognize logical groups | Add parentheses per rule |
| Not checking null before deep access | Error during evaluation | Use an appropriate short-circuit guard or safe navigation |
| Calling methods with side effects in conditions | Results depend on order and short-circuiting | Move actions outside the expression |
| One expression contains too many nesting levels | Hard to review and test | Split into named methods or variables |
| Using mutable context variables across multiple requests | State can leak between evaluations | Create contexts scoped to usage and manage their lifecycle |

## 12. Summary

To write readable and maintainable SpEL conditions:

- Use **&&** and **||** deliberately, leveraging short-circuiting to guard null accesses.
- Factor out shared conditions instead of repeating the same predicate across multiple branches.
- Use clearly named variables in EvaluationContext, properties, or methods when a rule is reused.
- Avoid double negatives and prefer phrasing in affirmative states.
- Apply De Morgan's laws when it makes the conditional statement easier to understand, not merely for formal transformation.
- Use parentheses and test important true/false/null combinations.

When an expression exceeds what a short condition can express clearly, move the business rule portion to Java. SpEL should focus on combining clearly named values and predicates, so readers can understand the result without having to decode a long logical chain.