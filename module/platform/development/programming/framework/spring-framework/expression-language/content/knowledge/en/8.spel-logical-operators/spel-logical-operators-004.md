# Short-Circuiting and Its Impact on the Right-Hand Side of an Expression

In SpEL, the logical operators AND and OR evaluate operands from left to right and use a short-circuit mechanism. This means the result of the left-hand side is sometimes already enough to determine the result of the entire expression; in that case SpEL skips evaluating the right-hand side.

This mechanism directly affects what happens in the right-hand side. If the right-hand side calls a method, reads a property whose getter causes a side effect, performs an assignment, or invokes a function, that part may not execute. Therefore, when writing logical expressions, it is necessary to consider both the Boolean value and the behaviors that may occur during evaluation.

## 1. What Is Short-Circuiting?

Short-circuit evaluation is a way of evaluating a logical expression without computing every operand if the result is already decided.

For AND:

- If the left-hand side is false, the entire AND operation is definitely false. The right-hand side does not need to be evaluated.
- If the left-hand side is true, the right-hand side must be evaluated to know the final result.

For OR:

- If the left-hand side is true, the entire OR operation is definitely true. The right-hand side does not need to be evaluated.
- If the left-hand side is false, the right-hand side must be evaluated to know the final result.

The following table shows the deciding conditions:

| Operator | Left-hand side | Is the right-hand side evaluated? | Result |
|---|---|---|---|
| AND | false | No | false |
| AND | true | Yes | Follows the right-hand side value |
| OR | true | No | true |
| OR | false | Yes | Follows the right-hand side value |

The key point is that skipping the right-hand side is part of the evaluation semantics, not merely a performance optimization. Actions placed in the right-hand side are also skipped.

## 2. Logical Operators in SpEL

SpEL supports keyword forms and symbol forms for logical operations:

| Meaning | Keyword | Symbol |
|---|---|---|
| AND | and | && |
| OR | or | \|\| |
| NOT | not | ! |

Example:

~~~text
enabled and verified
enabled && verified
cached or loadAvailable()
cached || loadAvailable()
not disabled
!disabled
~~~

Both ways of writing AND and OR have the same logical meaning. Choose a consistent style within the same group of expressions so readers can follow easily.

With AND, the right-hand side runs only when the left-hand side is true. With OR, the right-hand side runs only when the left-hand side is false. This rule applies to evaluated SpEL expressions, even when the right-hand side contains method calls or property accesses.

## 3. Left-to-Right Evaluation Order

SpEL evaluates the left-hand operand first. After obtaining the left-hand result, the logical operator decides whether the right-hand side needs to be evaluated.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "false and (10 / 0 > 1)"
);

Boolean result = expression.getValue(Boolean.class);

System.out.println(result); // false
~~~

The left-hand side is already false so the right-hand side is not evaluated. The division by 0 on the right-hand side is therefore not executed during this evaluation.

With OR, a similar situation occurs when the left-hand side is true:

~~~java
Expression expression = parser.parseExpression(
        "true or (10 / 0 > 1)"
);

Boolean result = expression.getValue(Boolean.class);

System.out.println(result); // true
~~~

The right-hand side is skipped because true OR any Boolean value produces true.

You should not rely on a right-hand side being skipped to hide an invalid expression or invalid data. If the condition on the left changes, SpEL may evaluate the right-hand side and the error will then appear.

## 4. Impact on Method Calls on the Right-Hand Side

The right-hand side can call methods on the root object, variables, or beans that the context allows accessing. If short-circuiting occurs, that method is not called.

Suppose the application has a check object:

~~~java
public class AccessCheck {

    private final boolean enabled;
    private int auditCalls;

    public AccessCheck(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public boolean recordAudit() {
        auditCalls++;
        return true;
    }

    public int getAuditCalls() {
        return auditCalls;
    }
}
~~~

The expression can be evaluated:

~~~java
ExpressionParser parser = new SpelExpressionParser();

AccessCheck check = new AccessCheck(false);
EvaluationContext context =
        new StandardEvaluationContext(check);

Expression expression = parser.parseExpression(
        "enabled and recordAudit()"
);

Boolean result = expression.getValue(context, Boolean.class);

System.out.println(result);             // false
System.out.println(check.getAuditCalls()); // 0
~~~

Because enabled is false, SpEL does not call recordAudit(). The counter remains 0. If enabled is true, the recordAudit() method is called and the method's result determines the result of the AND operation.

This is important to note when a method has behaviors such as logging, incrementing a counter, updating state, sending notifications, writing to a database, or calling an external system. Placing a method on the right-hand side of AND does not guarantee it will always run.

## 5. Impact on Method Calls on the Right-Hand Side of OR

With OR, the method on the right-hand side runs only when the left-hand side is false.

For example, a cache may check whether data is already ready:

~~~java
public class CacheProbe {

    private final boolean cached;
    private int remoteCalls;

    public CacheProbe(boolean cached) {
        this.cached = cached;
    }

    public boolean isCached() {
        return cached;
    }

    public boolean loadFromRemote() {
        remoteCalls++;
        return true;
    }

    public int getRemoteCalls() {
        return remoteCalls;
    }
}
~~~

Expression:

~~~java
Expression expression = parser.parseExpression(
        "cached or loadFromRemote()"
);
~~~

If cached is true, the result is already determined to be true and loadFromRemote() does not run. Only if cached is false does SpEL call the method on the right-hand side.

This can be useful when the right-hand side is a costly operation that only needs to be performed when the left-hand condition is not met. However, if the right-hand side has important side effects, do not let its execution depend on a logical condition that readers might misunderstand.

## 6. Getters and Property Accessors Can Also Be Skipped

It is not only directly called methods that can have side effects. When SpEL reads a property, the accessor may invoke a getter on the object. If the getter performs a query, lazy-loads data, writes logs, or mutates state, reading the property can also produce observable behavior.

Example:

~~~text
active and profile.expensiveStatus
~~~

If active is false, SpEL does not need to read profile.expensiveStatus. The corresponding getter or accessor is not called during that evaluation.

Similarly:

~~~text
ready or remoteState.available
~~~

If ready is true, SpEL does not read remoteState.available.

This is why getters should be designed to return stable data with minimal side effects. A logical expression may be evaluated multiple times under different conditions; if a getter performs I/O or mutates state, behavior becomes unpredictable and hard to test.

## 7. Do Not Place Important Side Effects on the Right-Hand Side

Short-circuiting makes the execution count of the right-hand side depend on the data of the left-hand side. Therefore, do not use a logical expression as a place to enforce an important action.

For example, the following expression may fail to record an audit:

~~~text
authorized and recordAudit()
~~~

When authorized is false, recordAudit() is not called. If the business requirement is that every access attempt must be audited, perform auditing in a separate Java/service flow, and only then evaluate the condition. Do not use a logical operand as a mechanism to guarantee a side effect.

Similarly, the expression:

~~~text
isValid or saveFallback()
~~~

does not call saveFallback() when isValid is true. If saveFallback() persists data or sends a notification, that action only occurs in the branch where the left-hand side is false.

Keep SpEL expressions focused on checking and computation. Actions that mutate state, perform I/O, and communicate externally are usually better suited to a Java service, where ordering and errors can be controlled explicitly.

## 8. Use Parentheses to Express Condition Groups

When an expression has multiple AND/OR operators, parentheses help readers identify condition groups and which branch can be short-circuited.

Example:

~~~text
isAdmin or (isOwner and isActive)
~~~

If isAdmin is true, the entire right-hand group is skipped. If isAdmin is false, SpEL evaluates the group `isOwner and isActive`. Within that group, if isOwner is false then isActive is not evaluated.

Another example:

~~~text
isEnabled and (hasPermission or isPublic)
~~~

If isEnabled is false, the entire right-hand group is skipped. If isEnabled is true, SpEL evaluates hasPermission. If hasPermission is true, isPublic does not need to be evaluated.

When expressions are used in business rules, add parentheses even when operator precedence is already sufficient to determine the result. Parentheses help readers see the boundaries of each branch and predict which calls may occur.

## 9. Short-Circuiting Is Not an Access Control Mechanism

Short-circuiting should not be viewed as a security layer for expressions. It only decides whether an operand is evaluated during a specific invocation.

If users can edit expressions, they can change the left-hand side, invert the condition, or move a method call to another position. An expression might skip the right-hand side in one request, yet execute it in another request.

For untrusted expressions:

1. Restrict the root object and the data visible to the expression.
2. Restrict the methods, beans, functions, and property accessors allowed to be accessed.
3. Avoid exposing services capable of writing data or calling external systems.
4. Prefer SimpleEvaluationContext for limited data binding needs.
5. Do not rely on a Boolean condition to prevent a user from calling a sensitive method on the right-hand side.
6. Perform authorization checks and important side effects in the Java/service layer.

Short-circuiting can avoid an unnecessary call, but it does not replace authorization or sandboxing.

## 10. Each getValue Call May Take a Different Execution Branch

An Expression after parsing can be reused. However, each time getValue is called, SpEL still evaluates the expression with the data/context of that specific call.

Example:

~~~java
Expression expression = parser.parseExpression(
        "enabled and verify()"
);

Boolean first = expression.getValue(
        new StandardEvaluationContext(new Probe(false)),
        Boolean.class
);

Boolean second = expression.getValue(
        new StandardEvaluationContext(new Probe(true)),
        Boolean.class
);
~~~

On the first call, the right-hand side is skipped. On the second call, the right-hand side is evaluated. Reusing an Expression does not mean the result or short-circuit state is cached from the previous call.

This is especially important when the context contains variables or a root object that changes per request. Create an appropriate context for each evaluation and avoid sharing a mutable object if multiple threads may evaluate the expression concurrently.

## 11. How to Test Short-Circuit Behavior

When the right-hand side can produce a side effect, check both the expression result and whether the method was actually called. A true Boolean result is not enough to prove the branch executed as intended.

A simple approach is to use a test method with a counter:

~~~java
public class Probe {

    private final boolean left;
    private int calls;

    public Probe(boolean left) {
        this.left = left;
    }

    public boolean isLeft() {
        return left;
    }

    public boolean verify() {
        calls++;
        return true;
    }

    public int getCalls() {
        return calls;
    }
}
~~~

With the expression:

~~~text
left and verify()
~~~

test two cases:

| left value | Expression result | Number of times verify() is called |
|---|---|---|
| false | false | 0 |
| true | true | 1 |

With the expression:

~~~text
left or verify()
~~~

the test results are inverted:

| left value | Expression result | Number of times verify() is called |
|---|---|---|
| true | true | 0 |
| false | true | 1 |

You can add cases where the right-hand side returns false to confirm the AND/OR result, as well as a case where the right-hand side throws an exception to prove the exception only appears when that branch is actually evaluated.

## 12. Common Errors

| Symptom | Cause | How to handle |
|---|---|---|
| Method on the right-hand side does not run | The left-hand side already decided the AND/OR result | Check the left-hand value and short-circuit rules |
| Audit or counter does not increment | Side effect was placed in a branch that can be skipped | Move mandatory actions to Java/service flow |
| Exception on the right-hand side appears only sometimes | The right-hand side is evaluated only when needed | Inspect the data that causes the branch to execute |
| Getter is not called | Property access on the right-hand side was short-circuited | Do not rely on getters to perform mandatory tasks |
| Expression with many AND/OR operators is confusing | Condition groups and evaluation order are unclear | Use parentheses and split the expression into named parts |
| Assuming a skipped method is protected | Short-circuiting depends on input values | Restrict permissions in EvaluationContext and the service layer |
| Different results between two calls | Root object or variables changed between evaluations | Check the context and input data of each getValue call |

## 13. Key Takeaways

Short-circuiting in SpEL causes AND to skip the right-hand side when the left-hand side is false, and OR to skip the right-hand side when the left-hand side is true. This skipping applies to the entire evaluation of the right-hand side, including method calls, getters, accessors, assignments, and behaviors that can cause side effects.

Place conditions that can decide the result on the left-hand side, use parentheses to clarify branches, and keep expressions primarily for data checking. If an action must necessarily occur, perform it in a separate Java/service flow rather than placing it on the right-hand side of a logical operation.