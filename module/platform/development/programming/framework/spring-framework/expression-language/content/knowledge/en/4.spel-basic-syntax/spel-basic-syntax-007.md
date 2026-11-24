# Parsing Order and Grouping with Parentheses in SpEL

When a SpEL expression has multiple operators, the result is not determined simply by reading from left to right. The parser applies operator precedence and syntactic structure to build the expression. Parentheses help writers proactively group parts that need to be computed or evaluated together.

Accurately understanding precedence and grouping helps avoid wrong conditions, wrong calculations, errors when combining operators, and hard-to-maintain expressions. This lesson goes from how the parser understands expressions, a precedence table for common operator groups, associativity, how to use parentheses, and a debugging workflow.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Explain why SpEL does not always evaluate expressions in left-to-right order.
- Read an expression with multiple operators and identify which part is grouped first.
- Use parentheses to change or clarify evaluation order.
- Distinguish operator precedence from operator associativity.
- Recognize parentheses used to group expressions and parentheses used in method calls, functions, or collection access.
- Write and test arithmetic, comparison, logical, conditional, and object access expressions with clear structure.

You should already know literals, #-prefixed variables, property access, method invocation, and basic SpEL operators. This lesson focuses on how to combine them in a single expression.

## 2. How Does the Parser Process an Expression?

When calling parseExpression, SpEL parses the input string and creates an Expression representing the structure of the expression. That structure reflects syntax rules, operator precedence, and groups created by parentheses.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("2 + 3 * 4");

Integer result = expression.getValue(Integer.class);
~~~

The result is 14 because multiplication has higher precedence than addition. You can picture the parser grouping the expression into:

~~~text
       +
      / \
     2   *
        / \
       3   4
~~~

If you want to add first and then multiply, add parentheses:

~~~java
Expression expression =
    parser.parseExpression("(2 + 3) * 4");

Integer result = expression.getValue(Integer.class);
~~~

The result is now 20. The structure is grouped into:

~~~text
        *
       / \
      +   4
     / \
    2   3
~~~

Key point: the parser determines the syntactic structure during parsing. EvaluationContext and runtime data provide the values to evaluate that structure; they do not automatically change operator precedence.

## 3. Precedence Order of Operator Groups

The following table presents the precedence order from highest to lowest for common operator groups in SpEL expressions. Access constructs such as properties, indices, and method calls are components of primary expressions, not all of them are binary operators.

| Precedence | Group | Common Components |
|---|---|---|
| High | Access and reference | dot property access, safe navigation, index, method call, # variable, @ bean, T(...) type |
|  | Unary | negation ! or not, unary plus and minus |
|  | Multiplicative | *, /, %, div, mod |
|  | Additive | +, - |
|  | Relational | <, >, <=, >=, lt, gt, le, ge, between, matches, instanceof |
|  | Equality | ==, !=, eq, ne |
|  | Logical AND | and, && |
|  | Logical OR | or, \|\| |
| Low | Conditional and Elvis | conditional expression ? : and Elvis ?: |
| Lowest | Assignment | = |

This table helps orient you when reading an expression. For expressions with multiple levels, use parentheses to express intent rather than forcing readers to memorize all precedence rules.

### 3.1. Multiplication and Division Before Addition and Subtraction

Example:

~~~text
10 + 6 * 2
~~~

The result is 22 because 6 * 2 is executed first.

~~~text
(10 + 6) * 2
~~~

The result is 32 because parentheses force the addition to be grouped first.

### 3.2. Comparisons Before Logical Operators

Example:

~~~text
#age >= 18 and #verified
~~~

The expression is interpreted as:

~~~text
(#age >= 18) and #verified
~~~

The comparison part is evaluated first, then the boolean results are combined with AND.

Similarly:

~~~text
#admin or #age >= 18 and #verified
~~~

Because AND has higher precedence than OR, the grouping is:

~~~text
#admin or ((#age >= 18) and #verified)
~~~

If the business intent is that the user must be verified and also be either an admin or of sufficient age, write it explicitly:

~~~text
(#admin or #age >= 18) and #verified
~~~

The two expressions can yield different results. Parentheses here help prevent logic errors that directly affect access permissions or business conditions.

### 3.3. Conditional Expression Evaluated After Logical Conditions

Example:

~~~text
#score >= 60 and #attendance >= 80 ? 'PASS' : 'FAIL'
~~~

The condition part is grouped before choosing one of the two branches. It can be written more explicitly:

~~~text
((#score >= 60) and (#attendance >= 80)) ? 'PASS' : 'FAIL'
~~~

This style is easy to read when an expression has multiple conditions. If the true or false branch itself contains another logical expression, group each branch separately to clarify scope.

## 4. Parentheses Change How Expressions Are Grouped

Parentheses have three main benefits:

1. **Override precedence:** the part inside parentheses is processed as a group before being combined with the outside part.
2. **Clarify intent:** readers immediately see which conditions or calculations belong to the same group.
3. **Reduce errors when modifying:** when adding a new condition, the current logical scope remains clear.

### 4.1. Grouping Arithmetic Operations

~~~text
#price * (#quantity + #bonusQuantity)
~~~

The expression calculates price by total quantity. If parentheses are omitted, multiplication will be performed before addition and the result may differ.

### 4.2. Grouping Logical Conditions

~~~text
(#role == 'ADMIN' or #role == 'MANAGER') and #active
~~~

The expression requires the account to be active and have one of the two roles. Parentheses define the role group before combining with the active status.

### 4.3. Grouping Nested Expressions

~~~text
((#subtotal - #discount) * (1 + #taxRate)) >= #minimum
~~~

The expression can be split into parts:

- Calculate subtotal after discount.
- Calculate the tax factor.
- Multiply the two results.
- Compare the final total against minimum.

For financial or business formulas with multiple steps, use intermediate variables in Java or split into small expressions if doing so makes testing and explanation easier.

## 5. Precedence Differs from Associativity

Precedence determines which operator is grouped first when there are multiple kinds of operators. Associativity determines how grouping works when multiple operators of the same precedence level appear consecutively.

Addition, subtraction, multiplication, and division normally associate from left to right in sequences of operators at the same level.

Example:

~~~text
20 / 5 * 2
~~~

Grouped as:

~~~text
(20 / 5) * 2
~~~

The result is 8.

Similarly:

~~~text
10 - 3 - 2
~~~

Grouped as:

~~~text
(10 - 3) - 2
~~~

The result is 5. If you want to subtract from right to left, write it explicitly:

~~~text
10 - (3 - 2)
~~~

The result is 9.

Do not confuse associativity with the mathematical properties of operations. Addition and multiplication are commutative in many arithmetic cases, whereas subtraction and division are not. Therefore, changing parentheses can change the result.

For nested conditional expressions or assignment expressions, proactively use parentheses to avoid relying on how readers remember associativity rules.

## 6. Parentheses in Methods, Functions, and Collection Access

Not every pair of parentheses has the job of grouping a large expression. SpEL also uses parentheses for method and function calls.

Example:

~~~text
#order.calculateTotal(#taxRate + 1)
~~~

The parentheses after calculateTotal contain the method's argument list. Inside an argument, parentheses can continue grouping calculations:

~~~text
#order.calculateTotal((#baseRate + #extraRate) * #factor)
~~~

Here there are two structural levels:

- The outer pair of parentheses defines the argument passed to the method.
- The inner pair of parentheses groups the addition before multiplication.

Similarly, when calling a function:

~~~text
#normalize((#firstName + ' ') + #lastName)
~~~

Parentheses around an argument do not replace precedence rules inside the argument.

For collection selection, square brackets define the predicate:

~~~text
#orders.?[(total > 100) and active]
~~~

Parentheses inside the predicate group the comparison, while square brackets define the element filtering condition. Inside the predicate, #this represents the current element.

## 7. Combining with Variables, Properties, and Safe Navigation

Property and variable references can appear in a logical or arithmetic expression. Group the calculation part before comparing:

~~~text
(#order.unitPrice * #order.quantity) >= #minimum
~~~

If nested property access can be null, safe navigation makes the expression return null at a nonexistent branch:

~~~text
#customer?.address?.city
~~~

When combining with Elvis to choose a default value, you can group the value-retrieval part before string concatenation or comparison:

~~~text
(#customer?.displayName ?: 'Guest') + ' - welcome'
~~~

Parentheses make clear that the result of safe navigation and Elvis is the part concatenated with the following string.

Do not expect parentheses to handle null. They only group syntax. To control null, you need safe navigation, Elvis, or appropriate checking logic.

## 8. Writing Readable Multi-Condition Expressions

Suppose the application decides whether to allow an order to be processed. Conditions include order status, amount, and user permissions.

Short expression:

~~~text
#order.active and (#order.total >= #minimum or #isAdmin)
~~~

How to read it:

1. Check whether the total amount meets the threshold or the user has admin permission.
2. Check whether the order is active.
3. Only when both parts are true is the result true.

If written as a long ungrouped string, readers easily confuse required conditions with alternative conditions. Use parentheses to distinguish:

- Conditions that must be true in all cases.
- Options where only one branch needs to be true.
- Exception conditions.
- Negated conditions.

Another example:

~~~text
#enabled and not (#status == 'BLOCKED' or #expired)
~~~

It can be written more clearly:

~~~text
#enabled and (not (#status == 'BLOCKED' or #expired))
~~~

When conditions relate to permissions, payment status, or access control, prefer explicit writing and write tests for each branch.

## 9. Parsing Expressions and Evaluating Results

An expression can be parsed without yet knowing the runtime values of variables. Then, pass EvaluationContext when evaluating:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "(#score >= 60 and #attendance >= 80) ? 'PASS' : 'FAIL'");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("score", 85);
context.setVariable("attendance", 90);

String result = expression.getValue(context, String.class);
~~~

The result is PASS.

You can change data in the context for another evaluation without rewriting the rule. This is useful when the expression is a fixed configuration while data changes per object.

Distinguish:

- Parsing checks syntax and builds the expression structure.
- Evaluating executes that structure with the root object, variables, functions, and permissions present in the context.
- Parentheses determine grouping during the parse step; variable values do not change grouping.
- An expression that parses successfully can still fail when evaluating if a variable has not been declared, a property does not exist, or data types are incompatible.

## 10. How to Debug Multi-Level Expressions

When an expression returns a different result than expected, shrink it piece by piece:

1. Parse and evaluate the arithmetic part separately.
2. Evaluate each comparison condition to Boolean.
3. Combine conditions with AND or OR.
4. Add the conditional expression to select the result.
5. Finally add property paths, methods, or collection operations.

For example, instead of immediately debugging the expression:

~~~text
(#order.total - #order.discount) >= #minimum and #customer.active
~~~

Test step by step:

~~~text
#order.total - #order.discount
~~~

~~~text
(#order.total - #order.discount) >= #minimum
~~~

~~~text
#customer.active
~~~

~~~text
((#order.total - #order.discount) >= #minimum) and #customer.active
~~~

If the individual parts are all correct yet the combined expression is wrong, recheck grouping and precedence.

You can use parentheses even when current precedence already gives the desired result. The goal is to make the expression self-explanatory regarding the writer's intent.

## 11. Common Mistakes

| Symptom | Common Cause | How to Fix |
|---|---|---|
| Calculation result differs from expectation | Multiplication/division takes precedence over addition/subtraction | Group the part to compute first with parentheses |
| OR condition causes true result unexpectedly | AND has higher precedence than OR | Group OR branches and required conditions |
| Ternary condition picks the wrong branch | Condition before ? was not grouped as intended | Put parentheses around the entire Boolean condition |
| Long expression is hard to read | Too many operators and property paths on one line | Group by business rule or extract intermediate variables |
| Method receives wrong argument value | Confusing method call parentheses with arithmetic grouping parentheses | Inspect the argument list separately and group expressions inside |
| Parse succeeds but evaluation fails | Variable, root object, or property is missing in context | Check runtime data and access permissions |
| Editing an expression changes old logic | Adding an operator without redefining grouping scope | Rewrite grouping explicitly and add tests |

## 12. Practice Exercises

### Exercise 1: Arithmetic

Predict the results of the following expressions, then run them with SpEL:

~~~text
2 + 3 * 4
(2 + 3) * 4
20 / 5 * 2
20 / (5 * 2)
~~~

Explain why the results differ.

### Exercise 2: Logical Conditions

Given the variables:

- #isAdmin = false
- #age = 20
- #verified = false

Compare:

~~~text
#isAdmin or #age >= 18 and #verified
~~~

and:

~~~text
(#isAdmin or #age >= 18) and #verified
~~~

Record the results and explain which condition is mandatory.

### Exercise 3: Multi-Branch Condition

Write an expression returning:

- GOLD when the customer has GOLD tier and the order meets the threshold.
- SILVER when the customer has SILVER tier and the order meets the threshold.
- OTHER in the remaining cases.

Group each tier's condition with parentheses to avoid confusion between AND and OR.

### Exercise 4: Debugging

Create an expression with nested properties, arithmetic, comparison, and ternary. Evaluate each part separately, then combine them. Try removing a pair of parentheses and record the case where the result changes.

## 13. Checklist Before Saving an Expression

- [ ] Have you identified which operators have higher precedence?
- [ ] Have you distinguished precedence from associativity?
- [ ] Have you clearly grouped calculations that must be performed first?
- [ ] Have you grouped AND/OR conditions according to the exact business rules?
- [ ] Have you put parentheses around the condition before a ternary when the expression is complex?
- [ ] Have you distinguished grouping parentheses from method/function call parentheses?
- [ ] Have you checked the root object, variables, and properties in EvaluationContext?
- [ ] Have you tested small parts before evaluating the whole expression?
- [ ] Do you have tests for true, false, and boundary data cases?
- [ ] Is the expression short and clear enough for others to maintain?

## 14. Conclusion

SpEL parses expressions according to syntactic structure and operator precedence. Parentheses allow overriding the default grouping, expressing intent, and keeping logic stable as expressions evolve. Distinguish precedence from associativity, verify AND/OR and ternary conditions with concrete examples, and use explicit grouping for important business rules. A good expression not only produces the right result but also helps readers immediately understand why it produces that result.