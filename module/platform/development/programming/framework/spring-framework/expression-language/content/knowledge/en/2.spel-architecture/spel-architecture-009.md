# The processing pipeline from expression text to final value in Spring Expression Language

Spring Expression Language (SpEL) takes an expression written as text, parses that text into an executable structure, and then evaluates that structure against application data. The final result is not computed immediately when the parser reads the string. It only emerges when the application requests evaluation of the expression in a specific context.

The entire process can be traced across six stages:

1. Receive expression text and parser configuration.
2. Tokenize and parse syntax.
3. Produce the expression tree (AST) and Expression object.
4. Prepare EvaluationContext together with the root object.
5. Evaluate AST nodes, look up data, and perform operations.
6. Return the value, or convert it to the type requested by the application.

## 1. Pipeline overview

~~~text
Expression text
       |
       v
ExpressionParser / SpelExpressionParser
       |
       v
Tokenizer: recognizes tokens
       |
       v
Parser: validates syntax and builds structure
       |
       v
AST (Abstract Syntax Tree)
       |
       v
Expression (SpelExpression)
       |
       | getValue(context, ...)
       v
EvaluationState + EvaluationContext + root object
       |
       v
AST nodes are evaluated
       |
       +--> read properties / variables
       +--> call methods / access types
       +--> execute operators / convert types
       |
       v
Object value
       |
       v
Return directly or convert to target type
       |
       v
Final result
~~~

The two halves of the pipeline have different responsibilities:

- **Parsing:** turns text into an object representing the expression's logic. Parsing validates syntax and prepares the structure, without yet computing values from concrete business data.
- **Evaluation:** executes the parsed structure against the root object and EvaluationContext. This is when SpEL reads data, invokes methods, applies operators, and produces a result.

## 2. Stage 1 — Receiving text and choosing a parser

Applications typically start with the ExpressionParser interface and use SpelExpressionParser as the concrete parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");
~~~

The string passed to parseExpression is SpEL language text. It can contain literals, property names, variables, method calls, operators, collection accesses, and many other constructs.

The parser can accept configuration via SpelParserConfiguration. This configuration adjusts certain behaviors during parsing or evaluation, such as auto-initializing null properties and auto-growing collections in supported situations. If no special behavior is required, the default configuration can be used.

At this step, the application only needs to hand the expression text to the parser. Data such as a specific order or the value of the minimum variable will be supplied at evaluation time.

## 3. Stage 2 — Tokenizer and parser processing the text

### 3.1. Tokenizer recognizes components

The tokenizer reads the character string and recognizes syntactic units such as:

- Identifier: property names or method names, e.g., total, status.
- Variable marker: the # symbol starting a variable name, e.g., #minimum.
- Literal: numbers, strings, booleans, null.
- Operator: symbols such as >=, &&, +, ==.
- Delimiter: parentheses, dots, commas, and other separator symbols.

For the expression:

~~~spel
total >= #minimum && status == 'PAID'
~~~

token groups can be recognized corresponding to the name total, comparison operator, variable minimum, logical operator, name status, equality operator, and string PAID.

Tokens are only syntactic units. They are not yet the values of properties inside a Java object.

### 3.2. Parser checks structure and precedence

The parser uses tokens to determine how components combine with each other. For example, it needs to know which comparisons belong to the && operator, which parentheses group a sub-expression, and which arguments belong to a method call.

For the example expression, the logical structure corresponds to:

~~~text
AND
|-- GREATER_THAN_OR_EQUAL
|   |-- PROPERTY: total
|   |-- VARIABLE: minimum
|
|-- EQUAL
    |-- PROPERTY: status
    |-- LITERAL: 'PAID'
~~~

This diagram shows the relationships between parts of the expression. It is neither the evaluation result nor does it hold actual values for total or minimum.

If the string has invalid syntax, an error can occur immediately at parseExpression. For example, missing operands or unbalanced parentheses prevent the parser from building a valid structure. This error group belongs to the parsing stage.

## 4. Stage 3 — AST becomes an Expression object

### 4.1. AST represents the expression as a tree

An AST (Abstract Syntax Tree) is a parent-child node structure describing the syntactic meaning of an expression. Each node represents a component or operation:

| Node type | Example | Responsibility during evaluation |
|---|---|---|
| Literal | 'PAID', 100, true | Provide a constant value |
| Property | total, customer.name | Read a property from the current object |
| Variable | #minimum | Retrieve a variable from EvaluationContext |
| Operator | >=, &&, + | Evaluate operands and apply the operation |
| Method call | customer.isActive() | Locate and invoke a matching method |
| Selection / Projection | items.?[...], items.![...] | Filter or transform collection elements |

The parser builds the nodes according to the expression's structure and precedence order. During evaluation, the nodes cooperate to produce the parent expression's value.

### 4.2. Expression is the interface the application uses for evaluation

After successful parsing, the parser returns an Expression object. With SpelExpressionParser, the concrete implementation object is SpelExpression and holds the parsed expression structure.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");
~~~

Applications usually interact through the Expression interface rather than calling AST nodes directly. The getValue(...) overloads are the primary entry points to ask SpEL to evaluate an expression.

One point to remember: the Expression object describes the parsed logic. It does not decide on its own which order total belongs to, what value the minimum variable holds, or whether this evaluation yields true or false.

## 5. Stage 4 — Preparing EvaluationContext and root object

When the application calls getValue(...), SpEL needs to know the evaluation environment. This environment is supplied via EvaluationContext and the root object.

Example:

~~~java
Order order = new Order(
    new BigDecimal("750000"),
    "PAID"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

In the example:

- order is the root object.
- total and status are looked up on the current object, which initially is order itself.
- minimum is a variable registered in the context and referenced via #minimum.

EvaluationContext can also provide the mechanisms needed to resolve operations in the AST:

| Context component | Job in the pipeline |
|---|---|
| PropertyAccessor | Read or write properties on objects |
| MethodResolver | Find a matching method when the expression calls a method |
| ConstructorResolver | Find a constructor when the expression creates an object |
| TypeLocator | Find a Java type in expressions such as T(java.time.LocalDate) |
| TypeConverter | Convert values when an operation requires conversion |
| BeanResolver | Resolve bean references if configured by the application |
| OperatorOverloader | Allow customizing certain operations |

StandardEvaluationContext supports rich mechanisms and configurability. SimpleEvaluationContext restricts certain features to suit cases requiring controlled access scope, such as data binding. The chosen context type affects which expressions can evaluate successfully.

### Root object, #root, and #this

The root object is the starting point for looking up properties without a variable prefix. SpEL provides two special variables:

- #root references the root object of the evaluation.
- #this references the object that is the current evaluation target. In selection or projection, the current object can be each collection element in turn.

Example:

~~~spel
orders.?[total >= #minimum]
~~~

Inside the filter condition, total is read on each element being examined. #this also points to that element, while #root retains the root object of the entire evaluation.

## 6. Stage 5 — AST is evaluated

This is when the expression text begins producing a result based on actual data.

When getValue(...) is called, SpEL sets up evaluation state (EvaluationState) from the appropriate EvaluationContext and root object. This state helps AST nodes access the context, root object, and current object during execution.

The process can be visualized as follows:

~~~text
Expression.getValue(...)
       |
       v
Create evaluation state
       |
       v
Evaluate root AST node
       |
       +--> evaluate left child node
       |
       +--> evaluate right child node
       |
       +--> look up data via context
       |
       +--> execute operation
       |
       v
Root node receives final value
~~~

### 6.1. Property node reads data

For the expression total, the property node requests reading total on the current object. SpEL uses a matching PropertyAccessor. In default configurations, Java property access is typically performed via reflection and built-in accessors.

If the root object is Order and has a getTotal() getter, SpEL can retrieve the corresponding value through the property access mechanism.

If the property cannot be found or cannot be read on the current object, evaluation can raise an error.

### 6.2. Variable node retrieves value from context

For #minimum, the variable node looks up the name minimum in EvaluationContext. The returned value is the BigDecimal registered by the application.

The difference between total and #minimum is important:

- total is a property name resolved on the current object.
- #minimum is a variable name resolved from the context.

### 6.3. Method Call node locates and invokes method

For an expression such as customer.isActive(), SpEL needs to find a matching method on the customer object. MethodResolver in the context participates in locating the method; once a callable method is identified, SpEL performs the call and receives the return value.

Method lookup also depends on the number of arguments, argument types, conversion mechanisms, and context access permissions.

### 6.4. Operator node evaluates operands

For the expression total >= #minimum, the comparison node needs the values of both operands:

1. Evaluate total to get the order total.
2. Evaluate #minimum to get the threshold.
3. Compare the two values according to SpEL operator rules.
4. Return a Boolean value.

For the logical && operator, SpEL combines the results of sub-expressions according to logical rules. Some logical operators use short-circuit evaluation: if the first operand already determines the result, the remaining operand may not need to be evaluated.

### 6.5. Type conversion during evaluation

Some operations require values to be converted to a compatible type. EvaluationContext provides TypeConverter to support conversions permitted by the environment.

Conversion may be involved when assigning values, passing arguments to methods, or performing operations requiring compatible types. Do not assume every data type can be converted for every operation. If no suitable conversion exists, evaluation can fail.

## 7. Stage 6 — Receiving and converting the final result

Once the root AST node finishes evaluating, SpEL obtains the value of the entire expression. This value can be a Boolean, Number, String, a Java object, a collection, or null, depending on the expression.

If getValue(context) is called without requesting a specific type, the application receives the result as an Object:

~~~java
Object value = expression.getValue(context);
~~~

If the expected type is known, the application can ask SpEL to return that type:

~~~java
Boolean eligible =
    expression.getValue(context, Boolean.class);
~~~

With overloads taking a target type, SpEL uses the context's conversion mechanism when needed and when possible. If the value is incompatible and cannot be converted, the call can throw an error.

Two things should be distinguished:

- **The value produced by the AST:** the output of the expression evaluation process.
- **The type requested by the application:** the result type requested via the getValue overload taking a Class parameter.

The target type does not alter the expression's logic. It specifies the format of the result the application wants to receive.

## 8. End-to-end example: from string to Boolean

Suppose the application has an Order class:

~~~java
public class Order {
    private final BigDecimal total;
    private final String status;

    public Order(BigDecimal total, String status) {
        this.total = total;
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }
}
~~~

The goal is to check whether an order's total meets the minimum threshold and has status PAID.

~~~java
// 1. Prepare business data.
Order order = new Order(
    new BigDecimal("750000"),
    "PAID"
);

// 2. Parse text into Expression.
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "total >= #minimum && status == 'PAID'"
);

// 3. Prepare EvaluationContext.
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

// 4. Evaluate AST and receive Boolean result.
Boolean eligible =
    expression.getValue(context, Boolean.class);
~~~

Processing flow of the example:

| Stage | Activity | Data or result |
|---|---|---|
| Receive text | Parser receives the condition string | total >= #minimum && status == 'PAID' |
| Tokenize and parse | Recognize names, variables, literals, and operators | Valid syntactic structure |
| Build AST | Create property, variable, comparison, and logic nodes | Expression tree |
| Create context | Set order as root object and register minimum | total = 750000, minimum = 500000, status = PAID |
| Evaluate | Read properties, variables, and perform two comparisons | true && true |
| Return result | Root node returns Boolean | eligible = true |

If minimum changes to 900000, the expression and AST remain unchanged. The new evaluation reads the new variable value, the first comparison returns false, and the final result is false.

This example shows that expression text only describes logic. The data in the context determines the result of each evaluation.

## 9. Parsing and evaluation have different error categories

Distinguishing the two stages helps isolate errors faster.

### Parsing errors

Errors occur when the parser cannot understand the text according to SpEL syntax, for example:

- Missing operand in an operation.
- Unbalanced parentheses.
- Invalid method call or collection access structure.
- Using an operator in the wrong position.

Errors typically appear right at parseExpression(...). When parsing fails, the application does not yet have a valid Expression to evaluate.

### Evaluation errors

Errors occur when the syntax is valid but the data or environment does not meet requirements, for example:

- A variable is referenced but not registered in the context.
- A property does not exist or is unreadable.
- The current object is null where a property access is needed.
- No matching method is found.
- The context does not support a feature required by the expression.
- A required type conversion cannot be performed.

These errors appear when calling getValue(...), after parsing has already succeeded.

A practical investigation approach is to determine precisely whether the error occurred in parseExpression or getValue, then check syntax, root object, variables, accessors/resolvers, and data types in turn.

## 10. Reusing expressions and context lifecycle

An application can parse a string into an Expression once and then re-evaluate it with multiple contexts:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");

StandardEvaluationContext firstContext =
    new StandardEvaluationContext(firstOrder);
firstContext.setVariable("minimum", minimum);

Boolean firstResult =
    expression.getValue(firstContext, Boolean.class);

StandardEvaluationContext secondContext =
    new StandardEvaluationContext(secondOrder);
secondContext.setVariable("minimum", minimum);

Boolean secondResult =
    expression.getValue(secondContext, Boolean.class);
~~~

In this usage pattern:

- Expression holds the parsed logic.
- Each context supplies the root object and variables for its corresponding evaluation.
- Each getValue call produces a result according to the data supplied at that moment.

A context can contain mutable state. In applications handling concurrent requests, manage contexts with an appropriate scope of work and avoid accidentally sharing root objects or variables across requests.

## 11. How to trace the pipeline when reading SpEL code

When encountering code that uses SpEL, you can trace these points:

1. **Find the input string:** is the expression built from a constant, configuration, or user data?
2. **Find the parser:** where does the code call parseExpression, and is there any special parser configuration?
3. **Find the Expression:** how is the expression object stored and reused?
4. **Find the getValue call site:** when is the expression actually evaluated?
5. **Find the context and root object:** what data is the root object, and which variables are registered?
6. **Find the access mechanisms:** are there custom accessors, resolvers, converters, or bean resolvers?
7. **Find the result type:** does the application receive Object or request a specific type?
8. **Find error handling:** where are parsing exceptions and evaluation exceptions handled?

This tracing approach connects configuration code with actual runtime results, rather than looking solely at the expression string.

## 12. Summary

- The parser receives text, tokenizes, and parses syntax to build an AST.
- The AST describes the structure and execution order of the expression's components.
- Expression is the object the application uses to request evaluation of the parsed structure.
- EvaluationContext and the root object provide the necessary data, variables, and access mechanisms.
- EvaluationState assists AST nodes during evaluation, including tracking the root object and current object.
- Property, variable, method call, and operator nodes cooperate to produce the expression's value.
- getValue returns the result; overloads with a target type can convert the result according to the context's capabilities.
- Parsing errors occur when text cannot form a valid expression; evaluation errors occur when executing an expression against incompatible data or an incompatible environment.

When needing to explain a SpEL expression, walk from input to output: **what structure the text is parsed into, what data the context supplies, how the nodes are evaluated, and what type the final value is returned as.**
