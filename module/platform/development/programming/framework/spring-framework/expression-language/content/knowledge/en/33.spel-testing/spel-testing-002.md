# Testing the Parser with Valid and Invalid Expressions

The SpEL parser converts an expression string into an Expression object so the application can evaluate it later. Parser testing needs to verify two groups of inputs: expressions with valid syntax are parsed successfully, while expressions with invalid syntax are rejected with the appropriate parse error. The parse step must be separated from the evaluate step, because an expression can be syntactically valid yet still fail at runtime due to missing properties, incompatible data types, or unresolvable types.

A good test suite helps detect configuration errors right when rules are loaded, records the position of invalid syntax, and distinguishes parser errors from runtime data errors. Both standard expressions and template expressions should be tested if the application uses a ParserContext.

## 1. Parse and evaluate are two separate phases

SpEL is typically used in the following sequence:

1. ExpressionParser receives the input string.
2. parseExpression() parses the syntax and creates an Expression.
3. The application provides an EvaluationContext or root object.
4. getValue() evaluates the expression and returns the result.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("total >= 100");

    Boolean accepted =
            expression.getValue(order, Boolean.class);

The parseExpression() call checks the syntactic structure and builds an Expression. It does not necessarily read the total property or validate all runtime data. Those operations occur when getValue() is called.

Therefore, successful parsing should not be treated as proof that the expression will definitely succeed with every root object. Parser testing and evaluation testing must have distinct goals.

## 2. What is a valid expression?

A valid expression is a string that conforms to the SpEL syntax accepted by the parser of the Spring version in use.

Some examples:

    1 + 2

    'Spring Framework'

    total >= 100

    #minimumTotal > 0

    customer.active and customer.score >= 80

    T(java.lang.Math).max(10, 20)

The expressions above can be parsed without providing a root object. However, to evaluate expressions containing properties, variables, or type references, the application needs the appropriate context and data.

Successful parsing can be verified with assertDoesNotThrow:

    ExpressionParser parser = new SpelExpressionParser();

    assertDoesNotThrow(
            () -> parser.parseExpression("1 + 2"));

This verification approach is suitable when the test's goal is solely to confirm syntax. If you also want to verify the result, call getValue() and assert the returned value.

## 3. Invalid expressions and SpelParseException

When a string does not conform to SpEL syntax, the parser typically throws SpelParseException, a type of Spring Expression ParseException.

Examples of syntactically invalid strings:

    total >

    customer.name(

    (1 + 2

    'unterminated

These strings are missing an operand, a closing parenthesis, or a closing quote. The parser cannot create a valid Expression, so parsing fails.

Test example:

    ExpressionParser parser = new SpelExpressionParser();

    assertThrows(
            SpelParseException.class,
            () -> parser.parseExpression("total >"));

Do not just check that any RuntimeException is thrown. Checking for SpelParseException makes the test express the right contract: syntactically invalid input must be rejected at the parse phase.

Error messages can change between Spring versions. Avoid locking tests to the full message string unless specifically required; message content and error position may differ across versions or localization.

## 4. Writing unit tests for valid expressions with JUnit 5

JUnit 5 provides assertDoesNotThrow to confirm the parser accepts the input. A simple test can be written:

    import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

    import org.junit.jupiter.api.Test;
    import org.springframework.expression.ExpressionParser;
    import org.springframework.expression.spel.standard.SpelExpressionParser;

    class SpelParserTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @Test
        void parsesValidArithmeticExpression() {
            assertDoesNotThrow(
                    () -> parser.parseExpression("1 + 2"));
        }
    }

This test only checks syntax. If you want to confirm the expression also returns the right result:

    @Test
    void evaluatesValidArithmeticExpression() {
        Expression expression =
                parser.parseExpression("1 + 2");

        Integer result = expression.getValue(Integer.class);

        assertEquals(3, result);
    }

The two tests have different purposes: the first test verifies the parser, and the second test verifies both the parser and the evaluator.

## 5. Using parameterized tests for multiple valid expressions

When there are many expressions to check, JUnit 5 supports @ParameterizedTest and @ValueSource. As a result, a single test method can run with multiple input strings.

    import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

    import org.junit.jupiter.params.ParameterizedTest;
    import org.junit.jupiter.params.provider.ValueSource;

    class ValidSpelExpressionTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @ParameterizedTest
        @ValueSource(strings = {
                "1 + 2",
                "'Spring'",
                "total >= 100",
                "#minimumTotal > 0",
                "customer.active and customer.score >= 80"
        })
        void parsesValidExpressions(String source) {
            assertDoesNotThrow(
                    () -> parser.parseExpression(source));
        }
    }

This list should represent the syntax that the application actually uses: literals, arithmetic operators, comparisons, variables, property paths, and boolean logic.

If the system uses selection, projection, type references, or registered functions, add representative expressions for those features. Parsing does not require functions to exist in the context, but evaluation will require registering the right functions.

Parameterized tests also make it easy to add a new case without creating a separate test method for each string.

## 6. Testing syntactically invalid expressions with parameterized tests

@ValueSource can be used to confirm the parser rejects multiple invalid inputs:

    import static org.junit.jupiter.api.Assertions.assertThrows;

    import org.junit.jupiter.params.ParameterizedTest;
    import org.junit.jupiter.params.provider.ValueSource;
    import org.springframework.expression.spel.SpelParseException;

    class InvalidSpelExpressionTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @ParameterizedTest
        @ValueSource(strings = {
                "total >",
                "customer.name(",
                "(1 + 2",
                "'unterminated"
        })
        void rejectsInvalidExpressions(String source) {
            assertThrows(
                    SpelParseException.class,
                    () -> parser.parseExpression(source));
        }
    }

Each string must represent a clear syntax error. Avoid using an input that the parser can accept as a valid identifier just because the author thinks that property does not exist.

For example, unknownProperty is usually still valid syntax. The parser cannot know whether the runtime root object has that property or not. That is a case to verify in an evaluation test, not a parser test.

## 7. Distinguishing parse errors from evaluation errors

This is the most important point when building a test suite for SpEL.

**Parse errors** occur when the parser cannot build an Expression from the input string. Errors typically belong to SpelParseException.

**Evaluation errors** occur after the Expression has been created, when SpEL executes the expression with a specific root object, variables, or context. For example, a non-existent property can cause SpelEvaluationException.

Example:

    Expression expression =
            parser.parseExpression("missingProperty");

    StandardEvaluationContext context =
            new StandardEvaluationContext(new Order());

    assertThrows(
            SpelEvaluationException.class,
            () -> expression.getValue(context));

In the example, missingProperty is a syntactically valid property expression. The parser creates the Expression; the error only appears when the evaluator looks up the property on the Order root object.

Several other situations can also fail only at evaluation time:

- A variable or property returns null and is subsequently accessed.
- A type reference has valid syntax, but TypeLocator cannot find the class.
- A method exists in the expression, but there is no matching method resolver or arguments.
- Runtime data cannot be converted to the required type.
- A function has not been registered, or executing the function throws an exception.

Classify errors properly so tests point to the phase that needs fixing.

## 8. Testing parse and evaluate with a specific root object

A simple fixture can be used to test expressions that read properties and variables:

    class Order {
        private final BigDecimal total;

        Order(BigDecimal total) {
            this.total = total;
        }

        public BigDecimal getTotal() {
            return total;
        }
    }

Test:

    @Test
    void parsesAndEvaluatesOrderExpression() {
        Order order =
                new Order(new BigDecimal("150.00"));

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable(
                "minimumTotal", new BigDecimal("100.00"));

        Expression expression =
                parser.parseExpression(
                        "total >= #minimumTotal");

        Boolean result =
                expression.getValue(context, Boolean.class);

        assertEquals(Boolean.TRUE, result);
    }

This test verifies several parts at once: the parser accepts the syntax, the context supplies the variable, the root object has the total property, and the evaluator returns the expected boolean result.

Keep the fixture small so when the test fails, the cause can be identified. There is no need to use a database or start the entire Spring ApplicationContext for a simple parser unit test.

## 9. Checking Expression information after parsing

After successful parsing, the Expression object provides information about the received expression. The original string can be checked via getExpressionString():

    String source = "1 + 2";

    Expression expression =
            parser.parseExpression(source);

    assertEquals(
            source,
            expression.getExpressionString());

The evaluation result can be checked separately:

    assertEquals(
            3,
            expression.getValue(Integer.class));

Do not test the AST structure via reflection into internal SpEL classes unless writing integration tests for the framework itself or having a special reason. Internal classes may change between Spring versions. For applications, the contracts to verify are typically parse success/failure and evaluation results.

## 10. Testing template expressions with ParserContext

If the application uses template expressions, they must be parsed with the corresponding ParserContext. Valid syntax in template mode can differ from how the parser handles a standalone expression.

Example:

    Expression expression =
            parser.parseExpression(
                    "Hello, #{#name}!",
                    ParserContext.TEMPLATE_EXPRESSION);

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("name", "An");

    String result =
            expression.getValue(context, String.class);

    assertEquals("Hello, An!", result);

A template missing a closing brace can cause a parse error:

    assertThrows(
            SpelParseException.class,
            () -> parser.parseExpression(
                    "Hello, #{#name",
                    ParserContext.TEMPLATE_EXPRESSION));

When testing templates, always use the exact same ParserContext as in production. Do not parse a template using the default overload and conclude the template syntax is invalid.

If the application uses TemplateParserContext with custom prefix/suffix, the test must use the exact same delimiter pair.

## 11. Checking expressions with type references and functions

An expression can parse successfully even if a type or function is not yet available in the EvaluationContext.

Type reference example:

    Expression expression =
            parser.parseExpression(
                    "T(com.example.domain.Customer)");

The string can be parsed syntactically. Whether TypeLocator can locate the Customer class is an evaluation concern.

Similarly, a function:

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customer.code)");

The parser does not verify that the context has registered the normalizeCode function. When evaluating, the context must have the corresponding Method:

    context.registerFunction(
            "normalizeCode", normalizeMethod);

Therefore, there should be two kinds of tests:

- Parser tests confirming the syntax of type references/functions.
- Context integration tests confirming classes are resolved and functions are invoked successfully with real data.

With only parser tests, missing functions or wrong TypeLocator issues can still slip through to runtime.

## 12. Testing with SpelParserConfiguration

If the application uses SpelParserConfiguration, create the parser in tests with the same important configuration as production. Example:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.OFF,
                    getClass().getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression("total >= 100");

With IMMEDIATE or MIXED compiler modes, evaluation behavior and actual runtime types need separate testing. An expression parsing successfully does not mean it can definitely be compiled.

When the goal is solely to check syntax, OFF typically keeps tests focused on the parser and avoids mixing compilation overhead into the test. If production enables the compiler, have separate tests to confirm critical expressions work with that configuration.

Do not rely on internal invocation counts to force MIXED compilation in a unit test. Verify observable results and behavior, rather than testing unstable implementation details.

## 13. Organizing the test suite by error type

Tests can be organized into the following groups:

| Test group | What to verify | Error example |
|---|---|---|
| Valid parse | Expression is created successfully | None |
| Invalid parse | Parser throws SpelParseException | Missing parenthesis or operand |
| Valid evaluate | Expression returns the right result with context | Property and variable comparison |
| Invalid evaluate | Expression parses but fails at runtime | Non-existent property |
| Context integration | Functions, types, and resolvers are configured properly | Unregistered function |
| Template parsing | ParserContext and delimiters match | Missing template suffix |
| Compiler integration | Expression works with parser configuration | Runtime type changes |

This grouping makes test error messages meaningful. When a test fails, developers know whether to fix the expression string, data, context, or parser configuration.

## 14. Loading and validating rules from configuration

If the application stores expressions in files or a database, parse and validate syntax when loading rules rather than waiting for the first request to use them.

Example:

    Map<String, Expression> compiledRules =
            new HashMap<>();

    for (RuleDefinition rule : ruleDefinitions) {
        Expression expression =
                parser.parseExpression(rule.getExpression());

        compiledRules.put(rule.getId(), expression);
    }

If a rule has invalid syntax, an error can be reported with the rule ID and configuration loading stopped per application policy. For systems requiring partial availability, the faulty rule alone can be rejected and excluded from the active registry.

Distinguish parse/validation at startup from evaluation against each request's data. Not all runtime errors can be detected when loading rules, because the root object and variables may only exist when a request arrives.

Do not log the entire expression if it could contain secrets or sensitive data. Use the rule ID, error position, and necessary diagnostic details; restrict read permissions on the raw configuration.

## 15. Testing untrusted expressions

Parser tests are not a security mechanism. An expression that parses successfully can still call methods, read data, or use capabilities provided by the EvaluationContext.

If expressions are entered by users or administrators:

- Limit the length and number of stored expressions.
- Only allow authorized users to create or edit rules.
- Use an EvaluationContext with minimal capabilities, such as SimpleEvaluationContext for property-reading use cases.
- Do not place services, beans, or objects with broad privileges into the root/context unless needed.
- Also test valid expressions that should be rejected when exceeding permissions.
- Limit execution time and resources of the evaluation thread at the application level if rules can consume significant CPU.
- Log errors by rule ID and avoid exposing internal data.

Do not evaluate arbitrary expressions simply because the parser reported no error. Parsing validates syntax; access permissions and runtime impact must be controlled separately.

## 16. Comprehensive test suite example

A test class can combine valid parsing, invalid syntax parsing, and invalid property evaluation:

    class SpelParserTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @Test
        void acceptsValidExpression() {
            assertDoesNotThrow(
                    () -> parser.parseExpression("1 + 2"));
        }

        @Test
        void rejectsInvalidSyntax() {
            assertThrows(
                    SpelParseException.class,
                    () -> parser.parseExpression("total >"));
        }

        @Test
        void distinguishesEvaluationFailure() {
            Expression expression =
                    parser.parseExpression("missingProperty");

            StandardEvaluationContext context =
                    new StandardEvaluationContext(new Order());

            assertThrows(
                    SpelEvaluationException.class,
                    () -> expression.getValue(context));
        }
    }

The test class above illustrates three different outcomes:

- 1 + 2 has valid syntax.
- total > has invalid syntax, so it is rejected by the parser.
- missingProperty has valid syntax but does not exist on the root object, so it fails during evaluation.

In a real project, add imports, the Order fixture, and the needed business test cases. Keep parser tests independent of the Spring container when dependency injection is not needed.

## 17. Common pitfalls

| Practice | Problem | How to address |
|---|---|---|
| Only calling parseExpression and assuming the rule runs | Parsing does not verify all runtime data | Add evaluation tests with a real context |
| Using RuntimeException for all errors | Does not distinguish parse and evaluate | Check SpelParseException and SpelEvaluationException |
| Treating unknownProperty as invalid syntax | Identifier/property still has valid syntax | Check the error at evaluation time |
| Asserting the entire error message | Messages can change across versions | Check exception type and stable information |
| Parsing templates with the default overload | Parser does not use template delimiters | Pass the right ParserContext |
| Testing only literal expressions | Does not cover properties, variables, functions, or types | Use an expression set representative of production rules |
| Using a full Spring context for all parser tests | Tests are slow and environment-dependent | Use SpelExpressionParser directly when sufficient |
| Treating successful parsing as safe | Expressions can execute capabilities during evaluation | Restrict EvaluationContext and rule sources |

## Conclusion

Testing the SpEL parser needs to confirm that valid expressions are parsed successfully and syntactically invalid expressions are rejected with SpelParseException. At the same time, parse errors must be separated from evaluation errors: a string like unknownProperty can parse normally yet fail when the evaluator looks up the property on the root object.

Use JUnit 5 with assertDoesNotThrow, assertThrows, and parameterized tests to cover many cases. Test templates with the right ParserContext, test functions/type references at the context integration layer, and evaluate critical rules with realistic root objects and data. Successful parsing only verifies syntax; EvaluationContext, access permissions, and runtime behavior still need to be controlled and tested separately.