# Variables in Selection and Projection

In SpEL, selection and projection allow filtering or transforming each element of a collection. When an expression runs for each element, sometimes an external value outside the collection is needed as a condition or calculation parameter. For example, filtering order lines by a minimum quantity supplied from configuration, or calculating a discounted price based on a passed-in rate.

EvaluationContext allows registering named variables. In an expression, variables are referenced with the # prefix, such as #minimumQuantity or #discountRate. When using these variables inside selection and projection, distinguish them from #this and #root: application-supplied variables keep their name and value in the context; #this represents the current element; #root represents the root object of the evaluation.

## 1. Selection and Projection Operate on the Current Element

Selection uses the .?[...] syntax to keep elements matching a condition:

    lines.?[quantity >= 2]

Projection uses the .![...] syntax to compute a value for each element:

    lines.![product.name]

In both operations, SpEL sequentially evaluates the expression inside the brackets on each element of the collection. Unprefixed properties in that subexpression are typically read from the current element.

You can explicitly write the current object using #this:

    lines.?[#this.quantity >= 2]

    lines.![#this.product.name]

Writing #this makes it clear to readers that the property belongs to the element being processed. This is especially helpful when the expression also uses context variables or needs to access data on the root object.

## 2. Variables in EvaluationContext

A variable is a value put into EvaluationContext by the application under a specific name. With StandardEvaluationContext, variables can be registered using setVariable():

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", 2);
    context.setVariable("discountRate", new BigDecimal("0.10"));

In SpEL, those two variables are referenced with the # prefix:

    #minimumQuantity
    #discountRate

The variable name in the expression must match the registered name. The # prefix distinguishes a context variable from a property of the root object or a property of the current element.

Example:

    lines.?[quantity >= #minimumQuantity]

In this expression, quantity is a property of the current LineItem; #minimumQuantity is a variable passed into the context by the application. Each line item is compared against the same registered minimum threshold.

If you write minimumQuantity without #, SpEL looks for that property on the current object. It does not automatically treat it as a context variable.

## 3. Distinguishing #this, #root, and Application-Defined Variables

These three types of references serve different roles:

| Syntax | Meaning |
|---|---|
| #this | The current object being processed by the expression |
| #root | The root object of the entire evaluation |
| #minimumQuantity | The minimumQuantity variable registered by the application in context |
| quantity | The quantity property on the current object inside selection/projection |
| #root.customerTier | The customerTier property on the root object |

Suppose the root object is Order, which has a lines collection, a customerTier property, and an exchangeRate property. When evaluating:

    lines.?[#this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD']

- #this is the current LineItem.
- #this.quantity is the quantity of that line item.
- #minimumQuantity is the threshold registered in the context.
- #root.customerTier is the customer tier of the original Order.

#root does not change to a collection element when selection or projection begins. Conversely, #this changes with the element currently being processed.

## 4. Example: Using a Variable to Filter a Collection

Suppose the application has an Order class with a list of LineItem objects. Each LineItem has quantity and product. The rule needs to keep lines whose quantity meets a configured threshold.

Java prepares the root object and variable:

    Order order = orderService.findOrder(orderId);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", 3);

Selection expression:

    lines.?[quantity >= #minimumQuantity]

Evaluation:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "lines.?[quantity >= #minimumQuantity]");

    List<?> qualifyingLines =
            expression.getValue(context, List.class);

With a threshold of 3, lines with quantity of 3 or more are retained. The remaining lines are excluded from the selection result; the source collection is not modified.

You can use #this for extra clarity:

    lines.?[#this.quantity >= #minimumQuantity]

The two expressions are equivalent in this context. The #minimumQuantity variable holds the same value on every element evaluation during selection.

## 5. Example: Using a Variable in Projection

Projection can also use a variable as a parameter for a calculation. Suppose each LineItem has a BigDecimal unitPrice. The application passes in a price adjustment factor:

    context.setVariable(
            "priceFactor",
            new BigDecimal("1.05"));

Expression:

    lines.![#this.unitPrice.multiply(#priceFactor)]

Each line item is transformed into the price multiplied by a factor of 1.05. The result is a collection of BigDecimal values.

The full Java portion can be written as:

    Expression projection =
            parser.parseExpression(
                    "lines.![#this.unitPrice.multiply(#priceFactor)]");

    List<?> adjustedPrices =
            projection.getValue(context, List.class);

In this example, #this.unitPrice reads the price of the current line item; #priceFactor reads the shared variable supplied by the application. The transformation does not update unitPrice on LineItem.

Variables are especially useful when the same rule is evaluated over many elements while calculation parameters are decided externally, such as discount rates, score thresholds, effective dates, or region codes.

## 6. Combining Selection, Projection, and Multiple Variables

An expression can use multiple variables and both operations at once. For example, retrieving only the product names of line items whose quantity meets the threshold and whose order belongs to a GOLD customer:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ].![#this.product.name]

The process has two steps:

1. Selection checks each LineItem against quantity and the root object's customer tier.
2. Projection extracts product.name from each remaining line.

Another example calculates prices after applying a discount rate, but only for lines with a positive quantity:

    lines.?[#this.quantity > 0]
         .![#this.unitPrice.multiply(#discountFactor)]

Where discountFactor is a variable registered in EvaluationContext. You can change the variable's value when creating a context for another evaluation without rewriting the expression string.

When an expression has multiple conditions, wrap lines and use explicit #this or #root so readers can see the source of each value.

## 7. Variables Do Not Replace Element Properties

A context variable is external data passed into the expression. It does not automatically become a property of each collection element.

Example:

    lines.?[quantity >= #minimumQuantity]

Here, quantity belongs to LineItem, while minimumQuantity belongs to the context. If LineItem also has a minimumQuantity property, writing it without # accesses the property of the current LineItem:

    lines.?[quantity >= minimumQuantity]

The two expressions can yield different results. Use # before the variable name when you want to read the value registered by the application.

Similarly, if the root object has a customerTier property, you can write:

    #root.customerTier

Writing customerTier inside selection may look up the property on the current element. If LineItem does not have that property, the expression may fail. Use #root to state clearly that the value to read belongs to the original Order.

## 8. #this Changes Inside Nested Collections

When an expression enters a nested selection or projection, #this represents the element being processed in the current collection scope. Therefore, in multi-level nested expressions, you must identify which type of object #this points to.

For example, each Order has a lines collection and each LineItem has a discounts collection:

    orders.![lines.![#this.amount]]

In the outer projection, #this is the current Order. When the expression continues into the projection of lines, #this becomes the current LineItem. In the innermost projection, #this.amount is read on the current object of that collection.

#root still represents the initial root object of the evaluation and does not automatically switch to Order or LineItem simply because the expression goes deeper into child collections.

When you need to use root data in nested expressions, reference #root explicitly. If you need to hold and use multiple levels of intermediate objects in a very complex transformation, consider breaking down the processing in Java to avoid hard-to-follow expressions.

## 9. Variable Data Types and Null Values

A variable registered in context is a Java object. The runtime type of that value affects comparisons and computations in SpEL.

Example:

    context.setVariable("minimumQuantity", 3);
    context.setVariable("activeOnly", true);
    context.setVariable("cutoffDate", LocalDate.of(2026, 1, 1));

Expressions can use these variables directly:

    lines.?[quantity >= #minimumQuantity]
    lines.?[active == #activeOnly]
    records.?[createdAt >= #cutoffDate]

If a variable may be null, decide how to handle it before using it in comparisons or calculations. For example, if minimumQuantity may be null:

    #minimumQuantity != null
        and quantity >= #minimumQuantity

The and operator short-circuits; when the variable is null, the right-hand side does not need to be evaluated. However, this condition only makes sense if business logic defines null as selecting no elements. If null should use a default threshold, you can use Elvis:

    quantity >= (#minimumQuantity ?: 1)

Choose a clear null policy. Do not let a missing variable value accidentally cause a type conversion error or unexpected result.

## 10. Using Variables with Map in Selection and Projection

When selection or projection runs on a Map, the current element is a Map.Entry. You can use #this.key and #this.value to read the key and value.

For example, keeping only entries with a value greater than a threshold:

    #prices.?[#this.value > #minimumPrice]

Here, #minimumPrice is a context variable; #this.value is the value of the current entry. Selection on a Map retains entries that satisfy the condition.

Projection can create a collection of strings from keys and values:

    #prices.![#this.key + ':' + #this.value]

It can be combined with a formatting variable:

    #prices.![#this.key + ':' + #this.value + #suffix]

In this example, suffix is an application-supplied variable. Projection produces output values for each entry; it does not automatically build a new Map preserving the key-value structure.

## 11. Reusing Expression and EvaluationContext Lifecycle

If the expression string does not change, the application can parse it once and reuse the Expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "lines.?[quantity >= #minimumQuantity]");

On each evaluation, create or prepare an EvaluationContext with the corresponding root object and variables:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", requestedMinimum);

    List<?> result =
            expression.getValue(context, List.class);

This approach separates two parts: Expression represents the parsed rule; EvaluationContext supplies the data for the current evaluation.

Do not share a mutable context across concurrent requests if each request has a different root object or variables. One request can overwrite another request's variables if they share the context. Create a context per evaluation or manage updates and synchronization deliberately.

There is also no need to re-parse the expression just because variable values change. Simply evaluate the existing Expression with a context containing the new values, provided the syntax and meaning of the rule remain unchanged.

## 12. Complete Example: Filtering and Calculating Discounted Prices

Suppose Order has properties lines and customerTier. Each LineItem has quantity, unitPrice, and product.name. The application wants the names and discounted prices of lines whose quantity meets the threshold, only when the customer is GOLD tier.

Registering data:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", 2);
    context.setVariable("discountFactor", new BigDecimal("0.90"));

Selection expression:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ]

A projection expression can retrieve product names:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ].![#this.product.name]

If you need to create a descriptive string with both name and discounted price:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ].![
        #this.product.name + ': '
        + #this.unitPrice.multiply(#discountFactor)
    ]

Evaluating the expression with parser:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "lines.?[#this.quantity >= #minimumQuantity "
            + "and #root.customerTier == 'GOLD']"
            + ".![#this.product.name + ': ' "
            + "+ #this.unitPrice.multiply(#discountFactor)]");

    List<?> descriptions =
            expression.getValue(context, List.class);

The result depends on the order data and registered variables. When changing minimumQuantity or discountFactor, the application can re-evaluate the same Expression with a new context.

## 13. Common Mistakes When Using Variables in Selection and Projection

| Syntax or Situation | Cause | Resolution |
|---|---|---|
| minimumQuantity when intending to read a context variable | Missing # prefix | Use #minimumQuantity |
| #minimumQuantity has no value | Variable not registered or set to null | Check setVariable and null policy |
| #this.customerTier when property belongs to Order | #this is currently the collection element | Use #root.customerTier |
| #root.quantity inside selection | quantity belongs to the current element | Use #this.quantity or quantity |
| Variable mutated between requests | Mutable context shared | Create a separate context per evaluation |
| Comparison type error | Variable has incompatible type | Register the proper type and validate data |
| Nested expression misreads #this | #this changes with the current collection | Analyze each scope, use #root explicitly |

When encountering errors, determine which names are element properties, which are root object properties, and which are context variables. Then inspect the type and value of each variable before evaluation.

## 14. Limits and Security When Supplying Variables

Variables in EvaluationContext are part of the data the expression is allowed to use. Register only the values required by the rule.

Several principles:

- Pass concrete data types instead of unvalidated strings if the rule needs to perform calculations.
- Do not put sensitive information or objects with broad access into the context when the expression does not need them.
- Do not let external users freely choose variable names and values and evaluate arbitrary expressions.
- Define clearly which variables are required, which may be null, and default values if missing.
- Use a restricted-access context when only reading data is needed; configure StandardEvaluationContext deliberately if the rule needs advanced features.
- Test selection/projection with empty collections, null elements, null variables, and wrongly typed data.

Variables only supply data to the expression; they do not enforce business permissions on their own. The service must still authenticate the caller, control accessible data, and decide actions after receiving the rule result.

## Conclusion

In selection and projection, context variables allow passing external parameters into an expression without attaching them to every collection element. The application registers variables with setVariable(), while SpEL reads them using the # prefix. #this represents the current element; #root always represents the initial root object; unprefixed properties are read from the current object in the selection/projection scope.

When combining these references, clearly distinguish the source of each value, especially in nested collections. Parse the Expression once, supply an appropriate EvaluationContext per evaluation, define a null policy, and put only the necessary data into the context. That approach keeps rules reusable, configurable, and controllable in a Spring application.