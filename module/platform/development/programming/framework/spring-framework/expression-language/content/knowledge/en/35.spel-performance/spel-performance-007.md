# Limiting Expression Size and Input Data

A SpEL expression can be very short yet process huge amounts of data, or very long while only performing a few comparisons. Therefore, limiting the expression string size is necessary but not sufficient to protect application performance and resources. It is necessary to simultaneously control expression length, expression structure, quantity and size of input data, collection auto-grow behavior, parse count, and the cost of allowed functions.

The goal is for each rule to process only an amount of work within the budget the application accepts. Enforce limits right at the configuration or request boundary, provide small and clearly typed root objects, limit collections/strings, disable auto-grow if not needed, and monitor errors as well as evaluation time.

## 1. Two Types of Size to Control

There are two distinct groups of inputs:

- **Expression source:** the SpEL string the parser must analyze, e.g., total >= #minimumTotal.
- **Evaluation data:** the root object, variables, strings, collections, maps, and objects the expression accesses at runtime.

Limiting expression source prevents overly long or intentionally complex strings from entering the parser. Limiting evaluation data prevents a short expression like items.![name] from having to process hundreds of thousands of elements or produce an excessively large result.

For example, the following expression is very short:

    items.?[active].![name]

However, if items contains one million elements, selection and projection still have to process a huge amount of data. Conversely, a long expression containing many literals can take significant parse time even when input data is small.

Therefore, do not use a single limit to represent total SpEL cost. Set separate budgets for expression strings, data, collections, results, and evaluation frequency.

## 2. Limiting Expression Length

Expression length affects parse time, the memory needed to hold the string, and the expression structure. Applications receiving rules from files, databases, APIs, or administrators should check length before parsing.

In Spring Framework versions that support maximumExpressionLength (Spring Framework 6.2 and later), this limit can be configured via SpelParserConfiguration.

Example limiting expressions to 4,000 characters:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.OFF,
                    getClass().getClassLoader(),
                    false,
                    false,
                    128,
                    4_000);

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

The parameters in the example configure, in order: compiler mode, class loader, auto-grow null references, auto-grow collections, maximum auto-grow size, and maximum expression length. Choose limits based on real rules; 4,000 is only an illustrative value.

For Spring versions without a constructor supporting maximumExpressionLength, check at the application layer before calling the parser:

    private static final int MAX_EXPRESSION_LENGTH = 4_000;

    Expression parseRule(
            ExpressionParser parser, String source) {

        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                    "Expression must not be empty");
        }

        if (source.length() > MAX_EXPRESSION_LENGTH) {
            throw new IllegalArgumentException(
                    "Expression exceeds the configured limit");
        }

        return parser.parseExpression(source);
    }

Checking before the parser gives the application a consistent limiting policy across different Spring versions. String.length() measures length in Java UTF-16 code units; if an external API also has byte limits, check payload size under the encoding used as well.

## 3. Choosing Limits by Use Case

There is no single maximum length suitable for every type of rule. A rule comparing a few attributes typically needs fewer characters than a notification template or a multi-step calculation rule.

You can start by categorizing:

| Input Type | Limits to Consider |
|---|---|
| Simple boolean rule | Small expression length, few operators, and short property paths |
| Rule with selection/projection | Expression length and collection element count |
| Notification template | Template length, expression segment count, and result length |
| Administrator-created rule | Length, rule count, update frequency, and edit permissions |
| Expression from user request | Very tight limits or replace with a structured filter |

Collect existing valid expressions to understand the distribution of length and complexity. Set thresholds with headroom for valid rules, without setting thresholds so high that control is rendered ineffective.

If rules can be created by multiple groups, define limits per rule type or tenant when there is a business reason. All limits should be centrally configured and explainable, avoiding each service choosing a different number on its own.

## 4. Length Does Not Reflect Full Complexity

Two expressions of the same length can generate very different amounts of work. For example:

    total >= #minimumTotal

and:

    items.?[active and price > #minimumPrice]
         .![product.category.name]

The second expression accesses multiple property levels and traverses a collection. Runtime cost depends on element count, the object graph, and getter behavior.

Factors affecting complexity include:

- Number of operations and conditional branches.
- Depth of property paths.
- Number of nested selection/projection levels.
- Number of collection elements and map entries.
- Number of method or function calls.
- Length of strings compared or processed.
- Getter cost, lazy loading, and logic inside methods.
- Number of expression segments in a template.

SpEL does not provide a general CPU budget for all expressions. Length limits need to be combined with data limits and the set of permitted capabilities. For untrusted expression sources, restrict supported syntax or use a DSL/structured filter instead of allowing the entire SpEL language.

## 5. Limiting Data Before Creating EvaluationContext

Do not pass arbitrary payloads directly into the root object. Validate data at the API/service layer, then create a DTO containing only the fields the rule needs.

Example:

    public record OrderRuleInput(
            BigDecimal total,
            String customerTier,
            List<LineRuleInput> lines) {
    }

    public record LineRuleInput(
            String productCode,
            int quantity,
            boolean active) {
    }

Before creating the context, verify:

- The number of elements in lines does not exceed the threshold.
- productCode does not exceed the allowed length.
- total is within the business value domain.
- Required fields are not null.
- Collections do not contain null elements if the rule does not support that case.

Only then evaluate selection:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

    Expression expression =
            parser.parseExpression(
                    "lines.?[active and quantity > 0]");

    List<?> activeLines =
            expression.getValue(
                    context, input, List.class);

    boolean hasActiveLines = !activeLines.isEmpty();

DTOs limit the object graph visible to the expression and ensure data is validated prior to evaluation. For read-only rules, prefer a read-only context tailored to the needed property accessors. The empty-list check is done in Java, without needing to grant instance method invocation permissions in a read-only context.

## 6. Limiting Collections, Maps, and Projections

Selection and projection typically have cost scaling with input element count. A simple filter usually has to check each element; projection must produce an output value for each processed element.

Example:

    lines.?[quantity > #minimumQuantity]

    lines.![productCode]

If lines has N elements, the expression must walk through the corresponding elements. With nested collections, the amount of work can grow as the product of the level sizes.

Enforce limits before passing collections into the context:

    private static final int MAX_LINES = 500;

    if (input.lines() == null
            || input.lines().size() > MAX_LINES) {
        throw new IllegalArgumentException(
                "Too many order lines");
    }

The limit of 500 is only an example; choose values based on load and business needs. If data exceeds the threshold, consider filtering or aggregating in the repository/service first and passing a smaller result to SpEL.

It is also necessary to limit Map entry counts, element counts in nested collections, and projection result sizes. A short expression should not be able to produce an unbounded result list.

## 7. Limiting Strings and Textual Data

String operations can consume significant resources when inputs are very long. This applies to comparisons, concatenation, searching, case conversion, and regex.

Example:

    #input.matches(#pattern)

If input or pattern is supplied externally, limit the length of both. Some regular expressions can cause severe backtracking on specially crafted strings. Length limits help reduce risk but do not guarantee every regex is low-cost.

Do not concatenate a large string into the expression source to pass data. Instead, use variables or a root object:

    Expression expression =
            parser.parseExpression(
                    "customerCode == #expectedCode");

    context.setVariable("expectedCode", suppliedCode);

This keeps the expression stable and allows validating data length separately. If Unicode, whitespace, or case normalization is needed, perform it according to business rules before putting data into the context.

## 8. Controlling Auto-Grow for Null References and Collections

SpEL can be configured to automatically create objects when encountering null references or automatically grow collections when accessing an index beyond the current size. These features are convenient for data binding, but can increase the number of created objects or elements.

If a rule only needs to read data, it is usually best to disable both:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    false,
                    false,
                    128);

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

The first two flags disable auto-grow null references and auto-grow collections, respectively. Parameter 128 is the maximum auto-grow limit if the feature is enabled in another use case.

In Spring versions whose constructor also accepts maximumExpressionLength, both kinds of limits can be combined in one configuration:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.OFF,
                    getClass().getClassLoader(),
                    false,
                    false,
                    128,
                    4_000);

Do not enable auto-grow merely to avoid null or index errors in rules. Validate data at the application layer and handle nulls explicitly. If a data-binding use case genuinely needs auto-grow, cap the maximum size and test large, negative, or out-of-range indices.

## 9. Do Not Concatenate External Data into Expression Source

A common design mistake is building expressions by concatenating strings with request data:

    String source =
            "customerCode == '" + suppliedCode + "'";

    Expression expression =
            parser.parseExpression(source);

This approach turns input data into part of SpEL syntax. Quotes or special characters can alter the expression's meaning; at the same time, each distinct value creates a separate string that must be parsed and cached.

Parse a fixed expression and pass data via variables:

    Expression expression =
            parser.parseExpression(
                    "customerCode == #suppliedCode");

    StandardEvaluationContext context =
            new StandardEvaluationContext(input);

    context.setVariable("suppliedCode", suppliedCode);

    Boolean matches =
            expression.getValue(context, Boolean.class);

The expression source is now stable, while suppliedCode is treated as data. You still need to limit the length and validate suppliedCode per business rules, but the data cannot turn itself into SpEL operators or syntax.

## 10. Limiting Expression Count and Caches

Even when individual expressions are short, a system can exhaust memory if it accepts an unlimited number of distinct rules and retains every Expression in a cache.

For example, an unbounded cache keyed by source:

    Map<String, Expression> expressionCache =
            new ConcurrentHashMap<>();

If every request sends a new string, the cache can grow continuously. This creates a memory exhaustion risk even though each expression is below the length threshold.

Measures to apply:

- Limit the number of active rules per tenant or application.
- Only parse expressions that have been validated and are authorized to be saved.
- Use a cache with a capacity limit and eviction policy.
- Re-parse in a controlled manner when rules change, not on every request.
- Do not cache an EvaluationContext containing a root object or per-request variables.
- Monitor cache size, hit/miss rate, and parse counts.

If rules have a configuration lifecycle, you can parse on rule load and store the Expression alongside the rule ID. When a rule is deleted or changed, update the registry/cache accordingly to avoid retaining old expressions forever.

## 11. Limiting the Cost of Methods and Functions

An expression can be short yet call a time-consuming method:

    customer.loadFullProfile()

Or a function can execute queries, I/O, or large loops. Expression length limits do not control the cost inside methods.

For read-only rules:

- Do not put services or repositories in the root object.
- Only register functions with clear inputs/outputs.
- Prefer pure functions that perform no I/O or side effects.
- Limit the number of elements a function accepts and returns.
- Avoid methods that can load large object graphs or run unbounded queries.
- Do not allow untrusted expressions to call arbitrary methods.

SpEL does not provide a general timeout to safely stop any running expression. Running expressions on a separate executor does not create a sandbox on its own; interrupting a thread does not guarantee stopping Java code or I/O inside a method. The primary control is limiting syntax, data, and capabilities before evaluation.

## 12. Controlling Expression Depth and Structure

Length limits reduce input size but do not directly describe nesting depth or operation count. A relatively short string can still contain many parentheses, operators, or nested collections.

If rules come from an external source, an allowed syntax subset can be defined, for example:

- Literals, comparisons, and boolean operators.
- Property paths on a chosen DTO.
- A fixed set of named variables.
- A set of registered pure functions.
- Selection/projection only on bounded collections.

Reject or disallow constructs outside the use case's contract. If deeper structural analysis is required, build a validation layer or a DSL with its own grammar; do not use simple regexes to try to fully parse SpEL syntax.

Do not assume maximumExpressionLength is a limit on AST depth, node count, CPU, or method invocation count. It is an input string length limit. Other budgets must be controlled separately in the application.

## 13. Limiting Templates and Output Results

For template expressions, limit the entire template source, the number of expression segments, and the data substituted into each segment.

Example:

    "Hello, #{#userName}. Order: #{#orderNumber}"

Even if the segments are short, the result can be large if userName or orderNumber contains very long strings. Limit each field's size before rendering and limit total output length if the template is sent via email, logged, or returned by an API.

Do not use SpEL templates to arbitrarily assemble large payloads or untrusted content. If the goal is merely text placeholder substitution, a simpler template engine or formatter may be more suitable and easier to bound.

If results are written to a database or transmitted over a network, apply byte/encoding limits at the output layer, because character count and byte count are not always equal.

## 14. Handling Exceeded Limits

When an expression or data exceeds thresholds, reject early with an understandable error. Do not silently truncate strings, drop elements, or continue evaluating partial data if doing so could alter business meaning.

Example:

    if (source.length() > MAX_EXPRESSION_LENGTH) {
        throw new RuleValidationException(
                "Rule expression is too long");
    }

    if (input.lines().size() > MAX_LINES) {
        throw new RuleValidationException(
                "Rule input contains too many lines");
    }

At the API layer, map validation errors to an appropriate response and do not return internal stack traces. For rules loaded from configuration, log the rule ID and rejection reason so administrators can fix the configuration.

If the parser throws SpelParseException due to syntax or parser limits, retain the error location information needed for diagnosis. Avoid logging the full expression or input data if it may contain secrets or personal information.

## 15. Testing Size Boundaries

Limit testing should focus on points just below, exactly at, and just above the threshold.

Cases that should be included:

- Empty or whitespace-only expression.
- Expression shorter than the limit.
- Expression with length exactly equal to the limit.
- Expression one unit longer than the limit.
- Unicode strings with non-ASCII characters.
- Templates with many expression segments.
- Property strings near the length limit.
- Empty collection, collection at exact threshold, and collection exceeding threshold.
- Maps with many entries.
- Nested collections with large total element counts.
- Large indices when auto-grow is disabled or bounded.
- Projection producing results near the output limit.
- Regexes or functions that can take considerable time.

Example test for application-layer limits:

    @Test
    void rejectsExpressionAboveConfiguredLimit() {
        String source =
                "1".repeat(MAX_EXPRESSION_LENGTH + 1);

        assertThrows(
                RuleValidationException.class,
                () -> ruleParser.parse(source));
    }

Test valid cases right at the threshold as well to avoid setting limits too low or having off-by-one errors.

## 16. Monitoring Resources in Operations

Useful metrics include:

- Received expression length and count of rejected expressions.
- Parse time and parse count by rule ID.
- Evaluation time and evaluation count.
- Input collection/map sizes.
- String lengths and output result lengths.
- Number of Expressions in cache and hit/miss rate.
- Rates of SpelParseException and SpelEvaluationException.
- CPU, allocation, and heap when processing large rule groups.

Use rule ID or rule group to categorize metrics. Do not attach the full expression, root object, or sensitive payloads as metric labels because doing so can leak data and create huge cardinality.

When latency increases, inspect expression source, data size, and invoked methods/functions together. A short rule can still be slow due to getters querying a database or a spike in input collection size.

## 17. Common Mistakes

| Practice | Problem | How to Handle |
|---|---|---|
| Limiting only expression length | Collection/string data can still be huge | Set separate limits for data |
| Concatenating request values into expression source | Data can alter syntax and create many expressions | Use variables or a root DTO |
| Using an unbounded cache | Each new expression increases memory | Use a bounded cache and limit rule counts |
| Enabling auto-grow for all rules | Can create objects/collections beyond need | Disable by default or set maximumAutoGrowSize |
| Allowing unbounded collections | Selection/projection can process huge element counts | Limit data before evaluation |
| Using methods with I/O in expressions | Cost cannot be inferred from expression length | Provide only narrow, pure, budgeted functions |
| Treating parser length limit as a timeout | String limit does not bound evaluation CPU | Control data and capabilities |
| Truncating expressions exceeding threshold | Can alter rule meaning | Reject and require configuration fix |

## Conclusion

Limiting expression size is a necessary layer of protection, but it is not enough to control total SpEL cost. Limit expression sources, rule counts, string sizes, collections/maps, data depth, and output results. On supported Spring versions, configure maximumExpressionLength; on older versions, check length at the application layer. Disable auto-grow if rules are read-only and set maximumAutoGrowSize when a use case truly requires auto-expansion.

Keep expressions stable and pass data through variables or validated DTOs. Provide only narrowly scoped methods/functions, cache Expressions with bounds, reject inputs exceeding thresholds, and measure both parse and evaluation times. These limits should be chosen according to actual load and tested at boundaries so rules cannot inadvertently consume resources beyond the application's budget.