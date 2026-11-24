# Semicolons, Brackets, and Nested Structures

SpEL is an expression language. A SpEL string describes a value, a calculation, or a condition for Spring to parse and evaluate in a context. Its syntax has many symbols similar to Java, but each symbol has its own role. In particular, SpEL is not a miniature Java statement block: you cannot use semicolons to write multiple consecutive statements in the same expression.

When reading or writing long expressions, you must distinguish argument separators, expression grouping symbols, element access symbols, and data structure construction symbols. Understanding these roles accurately helps avoid parse errors and makes nested expressions easier to read.

## 1. Semicolons Are Not Used to Chain Multiple SpEL Statements

In Java, a semicolon ends a statement:

    int quantity = 3;
    int price = 100;

This is Java syntax. When calling the SpEL parser, the application passes in an expression string, such as:

    Expression expression = parser.parseExpression("quantity * price");

The part inside the string is SpEL; the semicolon ending the Java statement is outside the string. Do not put a semicolon inside to chain two independent expressions:

    quantity > 0; price > 0

The string above does not mean "check quantity then check price" like two Java statements. SpEL does not define the semicolon as a general statement separator. If you need to combine multiple conditions into one result, use a logical operator:

    quantity > 0 and price > 0

If you need to perform two independent evaluations, create two expressions and call the parser/evaluator separately for each expression in Java code:

    Expression quantityRule =
            parser.parseExpression("quantity > 0");

    Expression priceRule =
            parser.parseExpression("price > 0");

    Boolean validQuantity =
            quantityRule.getValue(context, order, Boolean.class);

    Boolean validPrice =
            priceRule.getValue(context, order, Boolean.class);

A semicolon can still appear as a normal character inside a string literal. Example:

    'A;B;C'

The expression above returns the string A;B;C; the semicolons are text data, not syntactic separators. The practical rule is: semicolons belong to Java syntax outside the SpEL string, or belong to string content when placed inside quotes; do not use them to combine multiple SpEL expressions.

## 2. Commas Separate Arguments and Elements

The comma is a common separator inside SpEL structures. It is used between arguments in a method call, between elements of an inline list, and between pairs in an inline map.

### Method Call Arguments

A method call can accept multiple arguments:

    priceService.calculate(subtotal, discountRate, taxRate)

Each argument is separated by a comma. Each argument itself can still be an expression:

    priceService.calculate(
        order.subtotal,
        order.customer.discountRate,
        order.tax.rate
    )

In this example, order.customer.discountRate and order.tax.rate are property access expressions. Commas only mark the boundaries between arguments passed to the method.

### List Elements

SpEL uses curly braces {} to create an inline list. Elements in the list are separated by commas:

    {10, 20, 30, 40}

A list can contain expressions instead of only literals:

    {order.subtotal, order.shippingFee, order.tax}

Lists can also be nested:

    {{'red', 'green'}, {'blue', 'yellow'}}

Each comma separates elements at the exact current bracket level. Commas inside an inner list do not terminate an element of the outer list.

### Map Key and Value Pairs

Inline maps also use {}, but each element has the form key:value:

    {name:'An', tier:'GOLD'}

A colon separates the key from the value; a comma separates this key-value pair from the next pair. A map can contain another map or list:

    {
        customer: {name:'An', tier:'GOLD'},
        limits: {maxOrders:10, regions:{'VN', 'SG'}}
    }

Here, customer and limits are two keys of the outer map. The value of customer is a nested map; the value of regions is a nested list.

## 3. Parentheses Are Used for Function Calls and Grouping Expressions

Parentheses () have two main roles: enclosing the argument list of a method/function call and grouping part of an expression to determine how it is computed.

### Enclosing Arguments

Method calls use parentheses, even when there are no arguments:

    order.calculateTotal()
    order.customer.getDisplayName()
    approvalRule.matches(order)

If there are multiple arguments, place them within the same pair of parentheses and separate them with commas:

    approvalRule.matches(order, currentUser)

The parentheses of one call can sit inside the parentheses of another call. These are nested calls:

    formatter.format(
        order.customer.getDisplayName(),
        order.calculateTotal()
    )

SpEL evaluates the argument expressions and passes the results to the outer call. When reading an expression, match each opening parenthesis with its corresponding closing parenthesis to know which call receives which arguments.

### Grouping Expressions to Control Evaluation Order

Parentheses also help group conditions. Example:

    (order.total >= 1000000 and order.customer.tier == 'GOLD')
        or order.customer.isVip

The first group requires both conditions on total amount and customer tier to be true together. Then the group result is combined with the VIP customer condition using or.

A calculation example:

    (subtotal - discount) * (1 + taxRate)

The two pairs of parentheses clarify that the discount must be subtracted first, and only then multiplied by the tax factor. If parentheses are removed, the expression may be interpreted according to default operator precedence and yield a different result.

You should use parentheses when an expression has multiple logical or arithmetic operators, especially when mixing and with or. Even though the language has precedence rules, explicit grouping lets readers see the intent immediately.

## 4. Square Brackets Are Used to Access and Filter Elements

Square brackets [] typically denote an access operation by index or by key.

For lists or arrays, indexing starts at 0:

    orders[0]
    orders[0].customer.name

For maps, use the key inside square brackets:

    settings['approvalLimit']
    officers['president'].name

For strings, you can access a character by index:

    customer.code[0]

SpEL also uses square brackets in collection selection and projection. Selection filters elements satisfying a condition with ?[...] after the collection name:

    orders.?[status == 'PAID']

Projection transforms each element into a selected value with .![...]:

    orders.![customer.name]

You can combine the two operations:

    orders.?[status == 'PAID'].![customer.name]

The expression above filters paid orders, then takes the customer name of each remaining order. The square brackets after ? contain the filter condition; the square brackets after ! contain the expression producing the output value.

## 5. Curly Braces Create Nested Lists and Maps

Curly braces {} can create an inline list or an inline map. The shape of the elements determines the desired structure:

- {1, 2, 3} is a list of elements.
- {name:'An', tier:'GOLD'} is a map of key-value pairs.
- {{1, 2}, {3, 4}} is a list containing lists.
- {customer:{name:'An'}, regions:{'VN','SG'}} is a map whose values are a map and a list.

A nested structure can be accessed by combining dots and square brackets:

    payload['customer'].name
    payload['regions'][0]

If payload is a map whose customer key holds an object or map with a name property, the first expression gets the customer name. The second expression gets the first element in the regions list.

Three types of brackets must be distinguished:

| Symbol | Common Role | Example |
|---|---|---|
| () | Method call or expression grouping | max(a, b), (a + b) * c |
| [] | Element/key access, selection, or projection | items[0], items.?[active] |
| {} | Creating an inline list or inline map | {1, 2}, {name:'An'} |

Brackets cannot be substituted for one another arbitrarily. For example, items(0) has the shape of a method call, whereas items[0] is element access by index.

## 6. Nested Structures: Reading from the Inside Out

A complex expression is often composed of smaller expressions. The easiest way to read it is to find the innermost bracket pair, determine the result of that part, and then work outward step by step.

Consider the expression:

    approvalService.isAllowed(
        order.customer.profile,
        order.lines.?[quantity > 0].![product.category]
    )

It can be analyzed by layers:

1. order.customer.profile accesses the customer's profile information.
2. order.lines.?[quantity > 0] filters order lines with a positive quantity.
3. .![product.category] transforms each remaining line into a product category.
4. approvalService.isAllowed(...) calls the check function with the customer profile and the generated list of categories.

The inside of a method call can contain property navigation, selection, and projection. Each part has its own brackets and delimiters; there is no need to flatten everything into a hard-to-read string.

Another example combining a map and a list:

    {
        customer: {
            name: order.customer.name,
            tier: order.customer.tier
        },
        paidItems: order.lines.?[status == 'PAID'].![product.name],
        summary: {
            subtotal: order.subtotal,
            total: order.total
        }
    }

This expression creates an outer map with three keys customer, paidItems, and summary. The values of customer and summary are nested maps; paidItems is a list created using selection and projection. The structure is nested to match the exact data to be represented.

## 7. Colons and Quotes Also Have Specific Roles

In an inline map, a colon separates key and value:

    {code:'VN', enabled:true}

In the ternary conditional operator, a colon separates the result when the condition is false from the result when the condition is true:

    order.total >= 1000000 ? 'PRIORITY' : 'NORMAL'

The structure of the operator is:

    condition ? valueWhenTrue : valueWhenFalse

Therefore, you need to look at the context to distinguish whether a colon is inside a map or inside a conditional operator.

String literals are enclosed in single or double quotes:

    customer.name == 'An'
    message.concat(" approved")

If a string uses single quotes and the content itself contains a single quote, SpEL allows writing two consecutive single quotes:

    'customer''s order'

Commas, semicolons, brackets, or colons inside a string literal are treated as text data. They no longer carry the syntactic separator role they have outside strings.

## 8. Whitespace and How to Format Long Expressions

SpEL allows spaces, tabs, and line breaks between tokens. Therefore, an expression can be wrapped across lines to clarify each group:

    (
        order.total >= 1000000
        and order.customer.tier == 'GOLD'
    )
    or order.customer.vip

Whitespace helps make formatting readable without changing the meaning of the expression, except for whitespace inside string literals. For example, 'GOLD MEMBER' is a string with an actual space.

When an expression is long, you should:

- Break lines at argument boundaries or list/map element boundaries.
- Indent each level of nested structure.
- Place clear parentheses around and/or groups.
- Use variable or property names with business meaning.
- Split an overly long expression into smaller rules in Java if it is hard to understand or hard to test.

There is no need to add a semicolon at the end of an expression just because surrounding Java code has semicolons. The SpEL string only contains the expression part that the parser needs to read.

## 9. Common Syntax Mistakes

| Syntax | Issue | Proper Syntax |
|---|---|---|
| a > 0; b > 0 | Using a semicolon to combine two conditions | a > 0 and b > 0 |
| calculate(a b) | Missing comma between two arguments | calculate(a, b) |
| {1; 2; 3} | Using semicolons in an inline list | {1, 2, 3} |
| {name 'An'} | Missing colon between map key and value | {name:'An'} |
| orders[0.customer.name | Missing closing square bracket | orders[0].customer.name |
| (a > 0 and b > 0 | Missing closing parenthesis | (a > 0 and b > 0) |

When the parser reports an error, do not look only at the last character in the message. Check from the error position back to the nearest enclosing structure: whether an opening bracket has been closed, whether a comma sits between two arguments/elements, and whether colons are present for key-value pairs or conditional branches.

## 10. Evaluation Example in Java

Suppose the root object has the properties total, customer.tier, and vip. You can parse a grouped condition expression and evaluate it as follows:

    ExpressionParser parser = new SpelExpressionParser();

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    String source =
            "(total >= 1000000 and customer.tier == 'GOLD') or vip";

    Expression expression = parser.parseExpression(source);

    Boolean allowed =
            expression.getValue(context, order, Boolean.class);

parseExpression receives a SpEL string. getValue receives the context, root object, and desired result type. Parentheses inside the string define condition groups; dots access nested properties. Semicolons terminate each Java statement outside the string and do not participate in the parsed expression.

In real applications, the context type must match the operations that the expression needs to perform. This example only reads properties, so it uses SimpleEvaluationContext with read-only data binding. If the expression needs broader capabilities, you must configure the context deliberately and restrict access appropriately.

## Conclusion

Punctuation in SpEL has clear responsibilities: commas separate arguments and elements; parentheses call methods or group expressions; square brackets access, filter, and transform elements; curly braces create lists or maps; colons separate key-value pairs or branches of the conditional operator. A semicolon is not a general statement separator in SpEL.

When structures are nested multiple levels deep, read from the inside out and maintain indentation corresponding to each bracket level. Understanding syntactic boundaries accurately helps the parser receive valid expressions while helping maintainers clearly see which data is accessed, which parts are grouped, and which result is passed to the next step.