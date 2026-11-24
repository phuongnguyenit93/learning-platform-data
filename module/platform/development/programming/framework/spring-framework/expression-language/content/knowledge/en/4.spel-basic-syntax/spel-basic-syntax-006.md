# Nested Expressions Inside Larger Expressions

## Objectives

After this lesson, you will be able to read and build a SpEL expression composed of multiple subexpressions; understand how operators combine, how to use parentheses to express evaluation order, and how to nest property access, method invocations, conditional expressions, or collection operations. You will also know how to read the #this and #root contexts when expressions are nested, as well as how to keep expressions maintainable.

## 1. Large Expressions Are Built from Subexpressions

Spring Expression Language (SpEL) lets you combine multiple small expressions into a larger expression. Each small part can produce a value, check a condition, access a property, or invoke a method. The result of one part can become the input for the next part.

Example:

~~~text
(#order.subtotal + #order.shippingFee) * (1 + #taxRate)
~~~

You can read the expression from the inside out:

1. Get the order's subtotal.
2. Add shippingFee.
3. Calculate the tax factor as 1 + #taxRate.
4. Multiply the pre-tax total by the tax factor.

The parts #order.subtotal + #order.shippingFee and 1 + #taxRate are subexpressions. The entire multiplication is the enclosing expression.

A large expression is not multiple SpEL strings automatically executed sequentially. The parser parses the entire syntax into one expression structure; when the application calls getValue(...), SpEL evaluates that structure and passes results between parts according to the rules of the language.

## 2. Using Parentheses to Group Expressions

SpEL has operator precedence. Multiplication and division are normally performed before addition and subtraction; comparisons are combined with logical operators according to the language's precedence rules.

Example:

~~~text
#subtotal + #shipping * #quantity
~~~

Multiplication is performed before addition. If you want to add the two amounts first and then multiply, group them with parentheses:

~~~text
(#subtotal + #shipping) * #quantity
~~~

Parentheses have two important roles:

- **Controlling evaluation order:** making clear which part must be evaluated first.
- **Clarifying intent:** helping readers recognize boundaries between subexpressions, even when default precedence already gives the same result.

Condition example:

~~~text
(#customer != null and #customer.active) or #isAdministrator
~~~

Group the first two conditions into one logical unit. The expression only evaluates to true if the customer exists and is active, or the current user is an administrator.

You should use parentheses when an expression has multiple logical operators or multiple nested calculations. This reduces the chance that readers misunderstand the evaluation order and makes changing the expression safer.

## 3. Nesting Property and Element Access

An expression can continue accessing deeper into the result of a preceding expression.

~~~text
#order.customer.address.city
~~~

SpEL reads customer, address, and city in turn from the order object.

You can combine property access with collection or map indexing:

~~~text
#orders[#selectedIndex].items[#itemIndex].price
~~~

This expression:

1. Gets the order at position #selectedIndex.
2. Gets the item at position #itemIndex in that order.
3. Reads the price of the item.

An index is also an expression. For example, you can compute an index using an arithmetic operation:

~~~text
#orders[#page * #pageSize + #offset]
~~~

When accessing multiple levels, each intermediate element must have a value and a type compatible with the next operation. If #orders is null, an index is out of bounds, or an element lacks the property to read, evaluation may raise an error.

If data can be null, consider the safe navigation operator:

~~~text
#order?.customer?.address?.city
~~~

The ?. operator avoids continuing access when the reference on the left is null. It can be combined with the Elvis operator to supply a default value:

~~~text
#order?.customer?.address?.city ?: 'No address yet'
~~~

Use safe navigation at positions that may be null according to the data model. It does not replace checking other errors such as invalid indices, wrong types, or calling nonexistent methods.

## 4. Nesting Method Calls and Arguments

The result of one method call can be used as the receiver object for the next call, or passed into another call.

~~~text
#order.getCustomer().getProfile().getDisplayName()
~~~

SpEL executes the calls in a chain. Method calling capability depends on EvaluationContext, the method resolver, and the application's access permissions.

An expression can also nest subexpressions inside an argument list:

~~~text
#pricingService.calculate(
    #order,
    #order.subtotal - #order.discount,
    #taxRate
)
~~~

In this example, subtraction is a subexpression evaluated to produce the second argument of calculate(...).

A more deeply nested call might look like:

~~~text
#formatter.format(
    #pricingService.calculate(#order, #taxRate)
)
~~~

The result from pricingService.calculate(...) becomes the argument to format(...).

Being able to call a method does not mean SpEL defines that method itself. Methods and business logic remain implemented in Java. Avoid nesting multiple calls with side effects inside one expression; maintainers will find it hard to see the call order, errors raised, and mutated state.

## 5. Nesting Conditional Operators

The ternary operator ? : lets you choose a value based on a condition. One branch can contain a larger expression or another ternary operator.

~~~text
#order == null
    ? 'MISSING'
    : (#order.total >= #threshold ? 'REVIEW' : 'NORMAL')
~~~

How to read it:

- If #order is null, return MISSING.
- If the order exists, continue evaluating the nested condition inside.
- If the total amount meets the threshold, return REVIEW; otherwise, return NORMAL.

Branches of the ternary operator are expressions, so they can contain arithmetic operations, property accesses, or method invocations.

Conditions can be combined with logical operators:

~~~text
#order != null and
    (#order.cancelled or #order.total >= #threshold)
~~~

When an expression becomes long, use parentheses and line breaks in the expression string to show structure. Do not nest many levels of conditions if you can define a named rule in Java or provide a meaningful variable from the context.

## 6. Nested Expressions in Selection and Projection

SpEL has operators for working with collections:

- Selection .?[...] filters elements satisfying a condition.
- Projection .![...] creates a new collection by evaluating an expression for each element.
- .^[...] retrieves the first element satisfying a condition.
- .$[...] retrieves the last element satisfying a condition.

The condition or projection part inside the square brackets is also an expression. Therefore, it can contain comparisons, property access, logical operators, or method calls.

For example, filtering orders whose total meets a threshold and then taking order IDs:

~~~text
#orders.?[total >= #minimum].![id]
~~~

You can nest selection to find orders that have at least one item carrying the target SKU:

~~~text
#orders.?[items.?[sku == #targetSku].size() > 0].![id]
~~~

How to read the expression:

1. Iterate over each order in #orders.
2. For each order, filter the items collection to find items whose sku equals #targetSku.
3. Get the number of found elements using size().
4. Keep the order if the element count is greater than 0.
5. Project the remaining list of orders into a list of id values.

### 6.1. Understanding #this and #root When Nesting Collections

In selection or projection, #this represents the current element being processed. When entering an inner nested selection, the current object changes to the element of the inner collection.

#root represents the root object of the expression evaluation and keeps its role as a reference to that root object. Therefore, do not confuse #this with #root in nested expressions.

Conceptual example:

~~~text
#orders.?[
    items.?[
        sku == #targetSku
    ].size() > 0
]
~~~

In the outer selection, #this is an order. In the inner selection, #this is an item. If the inner condition needs data from the root object, it can reference #root or a variable explicitly set in the context.

When reading a nested collection expression, identify which collection is being iterated at each .?[...] or .![...] pair. This avoids the mistake of using an order's property on an item, or vice versa.

## 7. Nesting Expressions Inside a Template Expression

SpEL also supports template expressions when the parser is created with TemplateParserContext or an appropriate ParserContext. A template can contain plain text and SpEL segments placed between delimiters.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Order #{#order.id} has total #{#order.subtotal + #order.shippingFee}",
    templateContext
);

String message = expression.getValue(context, String.class);
~~~

In the example, the entire string is a template. The two segments inside #{...} are SpEL expressions evaluated and inserted into the resulting text. Inside the second segment is a subexpression performing addition.

Distinguish:

- (#a + #b) * #rate is a SpEL expression containing subexpressions.
- "Total: #{#a + #b}" is only processed as a template if the parser receives a suitable ParserContext.
- An ordinary string literal containing #{...} is not automatically parsed recursively as a new expression.

If the application receives a string and wants to parse that string as a separate SpEL expression, Java code must actively invoke the parser again. Do not automatically evaluate untrusted strings just because they contain SpEL-like syntax.

## 8. How SpEL Evaluates Nested Expressions

The parser parses the entire expression and builds an internal structure representing operands, operators, properties, method invocations, and other elements. When calling getValue(...), SpEL evaluates parts according to semantic rules and dependency order based on the expression structure.

Some points to remember:

- Subexpressions produce values for the enclosing operation or call.
- Parentheses define expression groups and clarify order.
- The unselected branch of a ternary operator does not need to be evaluated to produce the result of the other branch.
- Logical operations can use short-circuit evaluation; for example, the right-hand side of and does not need to be evaluated if the left-hand side is already false.
- Collection selection and projection evaluate the inner expression for each corresponding element.
- An error in one subexpression can cause the entire evaluation to fail.

Do not rely on side effects to infer execution order of parts that have no guaranteed ordering relationship. Keep expressions focused on computation and data access; place state-changing workflows in clearly structured Java code.

## 9. Analyzing Errors in Nested Expressions

The more levels an expression has, the more places errors can occur. Errors can be divided into two groups:

### 9.1. Syntax Parsing Errors

The parser detects an error when the string does not follow SpEL syntax, for example:

- Missing closing bracket or parenthesis.
- Missing operand between two operators.
- Using the wrong delimiter for selection or projection.
- Writing invalid ternary operator syntax.
- Unbalanced string quotes.

Syntax errors are usually detected when calling parseExpression(...), before evaluating with actual data.

### 9.2. Evaluation Errors

An expression can parse successfully yet fail at runtime, such as:

- A null reference in a position that does not support safe navigation.
- A collection index out of bounds.
- An object lacking the requested property or method.
- An invoked method throwing an exception.
- Unable to convert the result to the target type.
- A collection containing an element without the structure expected by the expression.

When debugging, split the large expression into small parts and evaluate each part with representative data. You can create separate Expression objects for diagnostic purposes in Java code, or temporarily put intermediate results into context variables. Once the failing part is identified, reassemble the full expression.

There is no need to turn one long business expression into multiple parse calls in production. Splitting is only a technique to locate errors; the final implementation should fit the lifecycle and requirements of the application.

## 10. Keeping Nested Expressions Readable and Maintainable

A large expression can be shorter than many lines of Java, but the deeper it is nested, the harder it becomes to understand. Apply the following principles:

1. **Use meaningful variable names:** use #minimumTotal or #targetSku instead of hard-to-guess names.
2. **Group with parentheses:** clearly show related calculations and conditions.
3. **Use intentional line breaks:** each selection layer, condition, or large call should have recognizable boundaries.
4. **Avoid nesting too many calls with side effects:** an expression should mainly read data and produce a result.
5. **Move complex logic to Java:** if multiple business steps, loops, exception handling, or service coordination are needed, write a clearly named Java method.
6. **Control the context:** only provide the root object, variables, beans, and method resolvers that the expression actually needs.
7. **Test boundary data as well:** especially null, empty collections, invalid indices, and data types that can vary.

An expression like:

~~~text
#order != null and
    #order.customer != null and
    #order.customer.active and
    (#order.total >= #minimum or #order.priority)
~~~

can be easy to understand if grouped clearly. If the expression continues nesting multiple collections, service calls, and business conditions, consider moving that logic into Java and letting SpEL reference a single value or call one small controlled method.

## 11. Comprehensive Example

Suppose the application has a list of orders. The goal is to retrieve the IDs of orders that have a paid status and contain at least one item belonging to the selected SKU.

~~~text
#orders.?[
    status == 'PAID' and
    items.?[sku == #targetSku].size() > 0
].![id]
~~~

This expression combines multiple layers:

- The outer selection iterates over the orders.
- The first condition checks status.
- The second condition nests a selection on the items list.
- size() checks whether there is at least one matching item.
- The final projection retrieves the id of the retained orders.

The expression can be evaluated in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
    "#orders.?[status == 'PAID' and items.?[sku == #targetSku].size() > 0].![id]"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("targetSku", "SKU-100");

List<?> orderIds = expression.getValue(context, List.class);
~~~

In real applications, the data types of orders, items, and required properties must match the expression. If data is not guaranteed, handle null and check collections in the Java layer before evaluation.

## 12. Key Takeaways

Large SpEL expressions are composed of subexpressions. Subexpressions can be calculations, conditions, property accesses, index accesses, method invocations, selection, or projection. The result of one part can become an operand, argument, or condition for another part.

Parentheses help group expressions and clarify evaluation order. When nesting collections, track #this because the current object changes with the collection being processed; #root still references the root object of the evaluation.

The parser parses the entire syntax; SpEL does not automatically parse every resulting string recursively. Templates only work when using an appropriate parser context. Errors can appear during parsing or during evaluation with actual data.

Keep expressions concise, with parentheses and clear variable names. When nested structures begin to obscure business rules, move that logic into Java and let SpEL handle small, easy-to-understand configuration expressions.