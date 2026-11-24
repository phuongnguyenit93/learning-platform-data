# Parser, expression tree, and the parsing process

## 1. Where does the Parser sit in the SpEL architecture?

Spring Expression Language (SpEL) is an expression language that Spring uses to describe calculations, conditions, and operations on an object graph. An expression such as `order.total * (1 - discount)` looks like a short line of code, but Spring must understand its syntactic structure before it can compute the result.

The parser handles the step of converting a character string into a meaningful structure. That intermediate structure is commonly called an **expression tree** or **abstract syntax tree (AST)**. Once the AST is built, Spring can evaluate the expression against a concrete object and an `EvaluationContext`.

General flow:

    Expression string
          |
          v
    Parser / Tokenizer
          |
          v
    Token list
          |
          v
    Parsing according to grammar
          |
          v
    Expression Tree (AST)
          |
          v
    Expression
          |
          v
    EvaluationContext + root object
          |
          v
    Result value

Two stages need to be clearly distinguished:

- **Parsing** answers the question: is this string syntactically valid SpEL, and what is its structure?
- **Evaluation** answers the question: given the current data and context, what result does the expression produce?

The parser does not need to invoke business methods or read property values of real objects to build the AST. Those tasks belong to the evaluation stage.

## 2. Main components

### ExpressionParser

`ExpressionParser` is the public abstraction for parsing an expression. Application code typically depends on this interface to reduce coupling to a specific implementation.

The standard implementation is `SpelExpressionParser` in the `org.springframework.expression.spel.standard` package.

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("2 + 3 * 4");

    Integer result = expression.getValue(Integer.class);
    // result = 14

The `parseExpression` call creates an `Expression`. Calling `getValue` is what actually evaluates the expression.

### SpelExpressionParser

`SpelExpressionParser` is the standard entry point of SpEL. It accepts the input string, parser configuration if any, and returns the parsed expression object.

In Spring's implementation, the detailed parsing work is performed by an internal parser. When reading the source code, you may encounter components such as `InternalSpelExpressionParser`, the tokenizer, and token types. These are implementation details; normal application code only needs to use `ExpressionParser`.

### ParserContext

`ParserContext` tells the parser whether the input string is a standalone expression or a template containing embedded expression segments.

For a standalone expression, the parser treats the entire string as SpEL:

    parser.parseExpression("order.total > 1000");

For a template, plain text is kept as-is and only the parts inside the delimiters are parsed as SpEL:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Hello, #{#user.name}!",
        new TemplateParserContext()
    );

    String message = template.getValue(context, String.class);

`TemplateParserContext` uses `#{` and `}` as delimiters by default. You can pass a different `ParserContext` if the application needs its own delimiter convention. Do not confuse the `#{...}` delimiters of a template with thinking the parser always requires them for every standalone expression.

### SpelParserConfiguration

`SpelParserConfiguration` allows configuring several SpEL behaviors, such as the compiler mode and certain limits or behaviors that assist data access. The configuration is passed in when creating `SpelExpressionParser`.

    SpelParserConfiguration configuration =
        new SpelParserConfiguration();

    ExpressionParser parser =
        new SpelExpressionParser(configuration);

You should only enable extended behaviors after understanding their impact on data and performance. Parser configuration is not a substitute for designing an appropriate `EvaluationContext`.

### Expression and SpelExpression

`Expression` is the abstraction that applications use to get or set the value of an expression. `SpelExpression` is the SpEL implementation, holding the parsing result and coordinating evaluation.

With `SpelExpression`, the `toStringAST()` method is useful when you need to inspect the string representation of the AST for debugging. You should not rely on this string format as a stable serialization protocol.

### EvaluationContext

`EvaluationContext` provides the environment for evaluating the AST. It can contain:

- The root object that expressions access by default.
- Variables, for example `#minimum` or `#user`.
- Property accessors for reading or writing properties.
- Method resolvers and constructor resolvers.
- A type locator, bean resolver, and type conversion mechanism.
- Components that help control how expressions access data.

`StandardEvaluationContext` provides flexible access capabilities. `SimpleEvaluationContext` is designed for data binding cases where the set of allowed features needs to be restricted.

Key point: `EvaluationContext` is normally used during evaluation, not as a required input for the parser to build the syntactic structure.

## 3. From characters to tokens: lexical analysis

Before understanding an expression, the parser needs to recognize syntactic units. This process is called **lexical analysis**. The tokenizer reads the character string and produces tokens.

Example:

    2 + 3 * 4

Can be split into meaningful tokens:

| Input part | Meaning |
| --- | --- |
| `2` | Numeric literal |
| `+` | Addition operator |
| `3` | Numeric literal |
| `*` | Multiplication operator |
| `4` | Numeric literal |

A property access expression:

    customer.address.city

has recognized components such as identifiers and property access dots.

Depending on the syntax, the tokenizer needs to recognize groups such as:

- **Identifier:** property name, method name, variable name, or type name.
- **Literal:** number, string, boolean, and null.
- **Operator:** arithmetic, comparison, logical, assignment, and special SpEL operators.
- **Delimiter:** parentheses, square brackets, commas, and dots.
- **Keyword or specialized token:** keywords and symbols with specific meanings in the grammar.

A token typically stores its token type and position in the source string. This position helps the parser pinpoint which segment caused an error and produce messages that can point to the character location.

The tokenizer only recognizes syntactic units. It does not decide which operation executes first, nor does it know whether a property exists on an object at runtime.

## 4. Parsing: applying grammar and precedence

After obtaining tokens, the parser analyzes their order and relationships according to the SpEL grammar. The result is not just a list of tokens, but a nested structure.

An expression parser needs to handle at least the following:

1. Determining what is a sub-expression and what is a delimiter.
2. Applying operator precedence.
3. Applying left or right associativity according to the grammar.
4. Recognizing constructs such as method calls, property access, indexing, conditionals, and collection operations.
5. Detecting invalid syntax or incomplete expressions.

Example:

    2 + 3 * 4

Multiplication has higher precedence than addition. Therefore, the syntax tree has the form:

          +
         / \
        2   *
           / \
          3   4

This means the parser interprets the expression as:

    2 + (3 * 4)

and not as:

    (2 + 3) * 4

If you need to change the order, parentheses create an explicit nested structure:

    (2 + 3) * 4

When reading a complex expression, analyze from the high-precedence parts and nested structures first. Do not read an expression as a left-to-right string and assume all operators share the same precedence level.

## 5. Expression tree (AST)

The AST is the structural representation of an expression after parsing. Each node describes a syntactic element or an operation. A node can contain child nodes, allowing nested structure to be clearly represented.

For the expression:

    2 + 3 * 4

The AST can be visualized as follows:

    Plus
    |-- Literal(2)
    |-- Multiply
        |-- Literal(3)
        |-- Literal(4)

The root node is the addition operation. Its right branch is multiplication; the two literals 3 and 4 are children of the multiplication node. This tree preserves the precedence semantics determined by the parser.

Some node groups that can appear in a SpEL AST:

| Node group | Role |
| --- | --- |
| Literal | Constant values such as numbers, strings, booleans, or null |
| Operator | Arithmetic, comparison, or logical operations |
| Property/field reference | Accessing a property or field |
| Method reference | Representing a method call |
| Indexer | Accessing an element by index or key |
| Type reference | Referencing a type using SpEL syntax |
| Constructor reference | Representing an object creation operation |
| Ternary/Elvis | Conditional expressions and fallback values |
| Selection/projection | Filtering or transforming collection elements |
| Compound expression | Combining multiple consecutive access steps |

Example:

    customer.address.city

can be understood as a chain of consecutive accesses: starting from `customer`, getting `address`, then getting `city`. If one access step returns null, accessing the next step may fail at evaluation time, unless the expression uses appropriate safe navigation.

The AST is not a verbatim copy of the source. It describes syntactic meaning. Whitespace, equivalent notations, or unnecessary parentheses may not be preserved as originally typed by the author.

In the SpEL implementation, nodes are organized through abstractions such as `SpelNode` and concrete node implementations. `SpelExpression` holds the root node of the parsed expression. This is why the expression tree is the central structure connecting parsing with evaluation.

## 6. The parser does not execute the expression

Consider the example:

    account.balance >= 500

During parsing, Spring can determine:

- `account` is an object access part.
- `balance` is the next property.
- `>=` is a comparison operator.
- `500` is a numeric literal.
- The whole expression is a two-sided comparison.

However, the parser cannot conclude whether the expression returns true or false without an object and context to evaluate against.

When calling:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "account.balance >= 500"
    );

we already have an `Expression` object. For evaluation, we need to provide the corresponding variable or root object:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("account", account);

    Boolean allowed =
        expression.getValue(context, Boolean.class);

Here `#account` is the variable reference syntax in SpEL. Therefore, if a variable is used, the expression must be written as:

    #account.balance >= 500

A more complete example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("#account.balance >= #minimum");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("account", account);
    context.setVariable("minimum", 500);

    Boolean allowed =
        expression.getValue(context, Boolean.class);

The parser handles the syntax of `#account` and `#minimum`; the evaluation context provides the actual values of those two variables.

## 7. The evaluation process after the AST is built

When `getValue(...)` is called, SpEL coordinates the evaluation of the nodes in the AST. Depending on the node type, the process may need to:

- Read literals directly.
- Evaluate child nodes first and then apply the operator.
- Find an appropriate property accessor to read a property.
- Find a method resolver to select a callable method.
- Perform type conversion when required by an operation or method.
- Access collections, maps, or elements by index.
- Resolve the root object, variables, and functions in the context.

For example, with:

    #order.total * (1 - #discount)

SpEL needs to get the value of `order.total`, get the `discount` variable, compute the parenthesized part, and then perform the multiplication. The AST specifies the structure and order of operations; the context provides the data so that each node can be evaluated.

Properties or methods are only resolved when evaluation needs to access them. Therefore, an expression can parse successfully and still fail at runtime, for example due to a non-existent property, no matching method, a null value in a disallowed position, or incompatible data types.

## 8. Expression template

SpEL can be embedded into a text string. In this case, the parser needs to distinguish between plain text parts and expression parts.

Example:

    String source = "Order #{#order.id} has total #{#order.total}";

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        source,
        new TemplateParserContext()
    );

    String output = expression.getValue(context, String.class);

The template parser splits the source into text segments and expression segments inside the delimiters. The expression segments are parsed according to the SpEL grammar; text outside the delimiters is kept as static content.

Use a template when you need to interpolate expression results into message content. Use standard parsing when the entire input string itself is an expression.

## 9. Parse error and evaluation error

The two error types occur at two different times:

| Error type | Timing | Examples |
| --- | --- | --- |
| Parse error | When calling `parseExpression` | Missing parentheses, operator without operands, invalid syntactic structure |
| Evaluation error | When calling `getValue` or `setValue` | Non-existent property, non-invokable method, null access, type conversion failure |

A parse error is typically represented by `SpelParseException`. The error message can provide the position in the source string to pinpoint the problematic syntax segment.

An evaluation error is typically represented by `SpelEvaluationException`. This error indicates that the syntax was accepted, but it could not be executed with the current data or context.

When debugging, determine whether the error occurs on the `parseExpression` line or on the `getValue` line. If parsing fails, check the grammar, parentheses, literals, and token order. If evaluation fails, check the root object, variables, property accessors, method resolvers, null values, and data types.

## 10. Parsing, caching, and compiler

An expression is usually parsed once and used many times. Keeping the `Expression` object avoids re-parsing the same string on every request.

Example:

    private final ExpressionParser parser =
        new SpelExpressionParser();

    private final Expression eligibility =
        parser.parseExpression("#customer.active and #customer.score >= 80");

    public boolean isEligible(Customer customer) {
        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("customer", customer);

        return Boolean.TRUE.equals(
            eligibility.getValue(context, Boolean.class)
        );
    }

This example retains the `Expression` after initialization. Each evaluation still needs a context suitable for the data of that invocation. Do not share a context with mutable state across concurrent requests unless access safety is controlled.

SpEL also has a compiler to optimize certain expressions when eligible. Common compiler modes are `OFF`, `IMMEDIATE`, and `MIXED`. The compiler can generate a faster execution implementation for supported expressions. Not every SpEL construct can be compiled; in an appropriate mode, the framework can fall back to the standard evaluation mechanism when compilation is not possible.

The compiler is a post-parsing execution optimization step. It does not change the role of the AST in representing syntactic structure.

## 11. How to debug the parser and AST

When you need to understand a hard-to-read expression, follow these steps:

1. Keep the original expression source string so you can cross-reference error positions.
2. Call `parseExpression` separately to verify whether the syntax is valid.
3. If using `SpelExpression`, inspect `toStringAST()` to observe the AST representation.
4. Try splitting the expression into smaller parts and parsing each part to find the node or construct causing the error.
5. Only after parsing succeeds, inspect the evaluation context and runtime data.
6. Check the desired result type when using the `getValue(..., desiredResultType)` overload.

Example:

    SpelExpressionParser parser = new SpelExpressionParser();

    SpelExpression expression =
        (SpelExpression) parser.parseExpression(
            "#order.total + #shipping.fee * 2"
        );

    System.out.println(expression.toStringAST());

Casting to `SpelExpression` here is for using the debug API specific to the SpEL implementation. If the code only needs to read the expression value, keeping the `Expression` abstraction type is more appropriate.

## 12. Restricting access permissions when evaluating expressions

Because SpEL can support property access, method calls, type references, object creation, and bean access depending on the context, you should not arbitrarily evaluate expressions supplied by untrusted users using a full-privilege context.

Some principles:

- Do not concatenate untrusted input directly into an expression string and evaluate it.
- Only put into the context the variables and objects that the expression actually needs.
- Use `SimpleEvaluationContext` when the business logic only requires a limited feature set.
- Configure property accessors or method resolvers strictly within the required scope.
- Do not enable broad access permissions just to make an expression work.
- Treat expression text as a form of input capable of executing logic.

The parser only validates and builds the syntactic structure. Restricting what an expression is allowed to access lies primarily in the evaluation context and the resolver/accessor components provided by the application.

## 13. Key takeaways

- `ExpressionParser` is the public abstraction; `SpelExpressionParser` is SpEL's standard implementation.
- The tokenizer recognizes syntactic units; the parser applies grammar, precedence, and associativity.
- The AST represents the expression structure using nested nodes.
- `Expression` is the parsing result that the application can retain and evaluate multiple times.
- `EvaluationContext` provides the root object, variables, and data access mechanisms during evaluation.
- Successful parsing does not guarantee successful evaluation.
- Template parsing allows mixing plain text with SpEL segments.
- The compiler can optimize certain expressions, but does not replace the responsibilities of the parser and AST.
- When accepting expressions from untrusted sources, permissions must be restricted in the evaluation context.

When reading or designing a flow that uses SpEL, clearly separate three questions: what structure the string is parsed into, what context that structure is evaluated with, and what that context allows access to. These three questions help pinpoint the right place to fix when an expression has syntax errors, wrong data, or exceeds intended access permissions.
