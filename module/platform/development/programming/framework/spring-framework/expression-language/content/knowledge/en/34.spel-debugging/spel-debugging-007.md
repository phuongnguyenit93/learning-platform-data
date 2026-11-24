# Distinguishing parse errors from evaluation errors in SpEL

When working with Spring Expression Language (SpEL), an expression can fail in two different phases: when the parser converts the source into an Expression object, or when the Expression is evaluated with specific data and EvaluationContext. These two error groups usually have different causes and fixes.

Parse errors usually involve grammar: missing operands, unbalanced parentheses/brackets, unclosed string literals, or wrong template delimiters. Evaluation errors occur after the expression has been created, such as unregistered variables, non-existent properties, unresolvable methods, null receivers, or incompatible data types. Properly distinguishing the phase helps find the root cause faster and avoids editing syntax when the issue lies in the context or runtime data.

## 1. Objectives and prerequisites

After this lesson, you can:

- Distinguish parse-time failure and evaluation-time failure.
- Recognize ParseException, SpelParseException, EvaluationException, and SpelEvaluationException.
- Understand why a wrong variable or property name may only fail during evaluation.
- Use position and error codes to diagnose expressions.
- Inspect root object, variables, property accessors, method resolvers, and type converters.
- Separate parsing and evaluation steps in code.
- Write tests for valid syntax, invalid syntax, and context-dependent failing expressions.
- Handle errors appropriately at configuration, application, and UI layers.
- Avoid masking errors by catching exceptions and returning inappropriate default values.

You should know how to create SpelExpressionParser, Expression, and EvaluationContext, and understand root objects, variables, property access, and method invocation.

## 2. Two phases in the expression lifecycle

The workflow for processing a SpEL expression consists of two main phases:

1. **Parse:** ExpressionParser reads the source, validates grammar, and creates an Expression object.
2. **Evaluate:** Expression uses EvaluationContext, root object, and runtime data to compute the result.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#order.total > 100");
~~~

The code above parses the expression. It does not yet need to know whether the order variable exists or whether the order object has a total property.

During evaluation:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);

Boolean allowed =
    expression.getValue(context, Boolean.class);
~~~

Only then does SpEL need to read the order variable, access total, perform the comparison, and convert the result to Boolean if needed.

Processing flow:

~~~text
Source string
     |
     v
parseExpression(source)
     |
     +---- invalid grammar ----> ParseException
     |
     v
Expression
     |
     v
getValue(context)
     |
     +---- data/context/runtime error ---> EvaluationException
     |
     v
Result
~~~

Successful parsing only confirms the source can be understood according to the grammar. It does not prove the expression can run with every context or every dataset.

## 3. What is a parse error?

A parse error occurs when the parser cannot construct an expression from the source. In SpEL, SpelParseException is the dedicated exception for syntax errors and extends ParseException from the Spring Expression API.

Missing operand example:

~~~java
parser.parseExpression("#amount *");
~~~

Unclosed string literal example:

~~~java
parser.parseExpression("'hello");
~~~

Unbalanced parentheses example:

~~~java
parser.parseExpression("(#price + #tax");
~~~

These errors appear during the parseExpression() call, before any EvaluationContext or runtime data is involved.

Common causes:

- Missing or extra parentheses, square brackets, or curly braces.
- String literal without a closing quote.
- Operator missing an operand.
- Misplaced comma or colon.
- Invalid list, map, selection, or projection syntax.
- Template syntax missing prefix/suffix or using the wrong ParserContext.
- Escaping altered at Java, XML, JSON, or storage layer before SpEL receives the string.

## 4. What is an evaluation error?

An evaluation error occurs after the parser has created an Expression, when the engine cannot compute a result in a specific context. SpelEvaluationException is the common dedicated exception in this phase and belongs to the EvaluationException family.

Syntactically valid expression example:

~~~text
#unknownVariable
~~~

This expression can parse successfully. Yet if the context lacks the unknownVariable variable, evaluation will fail.

Another example:

~~~text
#customer.nonExistingProperty
~~~

Property access syntax is valid, yet the actual customer object may lack that property or PropertyAccessor may not support access.

Common causes:

- Variable not registered or variable name mismatch.
- Root object is null or lacks the requested property.
- Wrong property path or getter is inaccessible.
- Method does not exist, is inaccessible, or arguments are incompatible.
- Bean reference cannot be resolved.
- Type reference cannot find the class.
- Constructor cannot be resolved.
- Type conversion fails.
- Null receiver at an unprotected position.
- Invoked method throws an exception.
- Property accessor or resolver denies access.

## 5. Quick distinction table

| Indicator | Parse failure | Evaluation failure |
|---|---|---|
| Timing | Inside parseExpression() | Inside getValue() or setValue() |
| Expression object | Not created successfully | Already created |
| Context needed | No context needed to detect invalid grammar | Typically depends on context and data |
| Example | #amount * | #missingVariable |
| Common exception | SpelParseException | SpelEvaluationException |
| Fix | Fix grammar/source | Fix context, model, data, resolver, or logic |
| Can parse before data exists? | Yes, if grammar is valid | Yes; error only appears at evaluation |

An error can look like a naming mistake yet belong to a different phase. For instance, writing customerName without # can be valid syntax and interpreted as a property on the root object. If the root object has no customerName property, the error only occurs at evaluation.

## 6. Example: same source area, errors in two phases

Parse error example:

~~~java
Expression expression =
    parser.parseExpression("#quantity +");
~~~

The parseExpression call throws SpelParseException because the expression is missing a right-hand operand.

Evaluation error example:

~~~java
Expression expression =
    parser.parseExpression("#quantity + 1");

StandardEvaluationContext context =
    new StandardEvaluationContext();

Integer result =
    expression.getValue(context, Integer.class);
~~~

The expression parsed successfully. The error occurs during evaluation because the quantity variable is not registered.

Fixing the context:

~~~java
context.setVariable("quantity", 4);

Integer result =
    expression.getValue(context, Integer.class);
~~~

The result is 5.

When debugging, always identify whether the exception came from the parse line or the evaluate line. Do not lump both into a single shared catch block if you need to give accurate feedback to configurators.

## 7. Analyzing error position and error code

SpelParseException provides diagnostic details such as the position where the parser detected the error, message code, and token-related details. SpelEvaluationException can also provide useful position or error code depending on the error kind.

Example:

~~~java
try {
    parser.parseExpression("#amount *");
}
catch (SpelParseException ex) {
    int position = ex.getPosition();
    Object messageCode = ex.getMessageCode();

    // Use position and messageCode for diagnostics.
}
~~~

During evaluation:

~~~java
try {
    expression.getValue(context);
}
catch (SpelEvaluationException ex) {
    Object messageCode = ex.getMessageCode();

    // Classify runtime error and record according to policy.
}
~~~

The error position helps narrow the region of source to inspect, though it is not necessarily where the author began making the mistake. For instance, a missing opening quote may cause the parser to detect an issue only at a later token.

Do not depend on full message text to drive logic. Messages can change across Spring versions or formatting. Use exception type, message code, and structured data for classification; human-readable messages are primarily for diagnostics.

If the source spans multiple lines, the application can map the offset to line/column for display in an editor. Account for how Java indexes strings by UTF-16 code units if the source contains Unicode characters outside the BMP.

## 8. Diagnosing variable and root object errors

If the expression references a variable with #name, verify the variable was registered in the exact context passed to getValue().

~~~java
context.setVariable("customer", customer);

Expression expression =
    parser.parseExpression("#customer.name");
~~~

Questions to check:

- Did the name in setVariable omit the # sign?
- Are you evaluating with the same context where the variable was registered?
- Is the variable value null or of the wrong type?
- Was the variable overwritten or removed before evaluation?
- Did the expression confuse a variable with a property of the root object?

For the root object, properties do not need the # prefix:

~~~text
customer.name
~~~

Whereas variables need the prefix:

~~~text
#customer.name
~~~

If an expression parses successfully yet reads the wrong data source, clearly verify the root object and variables. This is usually a context design mistake, not a grammar mistake.

## 9. Diagnosing property paths and null

A property path can have multiple layers:

~~~text
#order.customer.address.city
~~~

If an intermediate layer is null, further access can cause an evaluation failure. Check each object layer and use null-safe navigation at potentially null receivers:

~~~text
#order?.customer?.address?.city
~~~

The ?. sign protects the receiver immediately before it. If order is null, the remainder of the path is handled under null-safe semantics. If another property can also be null, place ?. at the appropriate position.

Distinguish between:

- Property does not exist: the model or accessor does not provide that property.
- Property exists but value is null: runtime data has no value.
- Root object is null: there is no object to begin accessing.
- Variable unregistered: context does not supply the variable name.

Null-safe navigation solves null receivers; it does not fix wrong property names or synthesize missing data.

## 10. Diagnosing method invocation

Example:

~~~text
#calculator.calculate(#amount)
~~~

If the expression parses yet evaluation fails, check:

- Is the calculator variable registered?
- Is the calculator value null?
- Does the calculate method exist and is it accessible?
- Is the argument count right?
- Is the runtime type of each argument compatible?
- Are there overloads making method resolution ambiguous?
- Does the method throw an exception internally?
- Does MethodResolver restrict that method?

A grammatically valid method call can still fail at runtime. If the method exists but throws an exception, inspect the cause inside the method rather than editing expression syntax.

Do not call methods with side effects in read-only expressions unless necessary. Side effects make reproducing errors and comparing results harder.

## 11. Diagnosing conversion and data types

An expression can parse and begin evaluating yet fail when a value must be converted to a target type.

Property assignment example:

~~~java
Expression expression =
    parser.parseExpression("retryCount");

expression.setValue(context, rootObject, "not-a-number");
~~~

If retryCount has a numeric type, TypeConverter may be unable to convert the string above into the property's type.

When encountering a conversion error, check:

- Runtime type of the source value.
- Target property or parameter type.
- TypeConverter attached to EvaluationContext.
- ConversionService and custom converters.
- Locale or format if data is numeric/date-time.
- Generic types if conversion happens inside a collection.

A conversion failure is not a ParseException. The source may be completely valid; runtime data is the cause.

## 12. Diagnosing bean references and type references

Bean reference:

~~~text
@pricingPolicy.calculate(#total)
~~~

If evaluation fails, check whether BeanResolver is configured, whether the bean name is correct, whether the bean exists in BeanFactory, and whether the method can be called.

Type reference:

~~~text
T(java.lang.Math).max(10, 20)
~~~

If evaluation fails, check whether TypeLocator can resolve the class and whether the static method is valid.

Both examples can parse successfully even when the context does not provide the corresponding resolver. The parser understanding `@beanName` or `T(...)` syntax does not mean runtime has permission or capability to resolve that object/class.

## 13. Separating parse and evaluate in code

Separating the two phases helps classify errors and display accurate messages:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (SpelParseException ex) {
    throw new InvalidExpressionSyntaxException(
        "Expression syntax is invalid", ex);
}

try {
    return expression.getValue(context);
}
catch (EvaluationException ex) {
    throw new ExpressionExecutionException(
        "Expression could not be evaluated", ex);
}
~~~

The domain exceptions in the example are application-defined. Depending on the system, you can keep the Spring exception as the cause for logging and diagnostics.

Benefits:

- Know whether the error occurred during parse or evaluation.
- Can parse/validate before publishing configuration.
- Can cache the parsed Expression.
- Each evaluation uses current context and data.
- Metrics and logs can distinguish syntax errors from runtime errors.

If the source comes from administrative configuration, parse on save or publish to catch grammar errors early. Runtime must still handle evaluation failures because data, permissions, and objects can change.

## 14. Step-by-step debugging workflow

When an expression fails, proceed in order:

1. Identify the line of code throwing the exception: parseExpression, getValue, or setValue.
2. Record the exception class and message code.
3. If a parse error, inspect source around position, parentheses/brackets, quotes, operators, and delimiters.
4. If an evaluation error, inspect context instance and root object.
5. Verify all required variables are registered with exact names.
6. Check each property path and null at each layer.
7. Check method signature, overloads, and MethodResolver permissions.
8. Check BeanResolver or TypeLocator if the expression uses @beanName or T(...).
9. Check TypeConverter if the error occurred during conversion.
10. Split long expressions into smaller parts to pinpoint the failing segment.
11. Reproduce with a minimal fixture having the same data types and state.
12. Write a regression test for the identified cause.

Do not change multiple components at once. If you change source, context, resolver, and converter in a single attempt, it is hard to tell which change resolved the error.

## 15. Parse once, evaluate many times

If the source does not change, you can parse once and reuse Expression:

~~~java
Expression expression =
    parser.parseExpression("#subtotal * (1 + #taxRate)");
~~~

Each evaluation can pass its own context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("subtotal", new BigDecimal("100"));
context.setVariable("taxRate", new BigDecimal("0.10"));

Object result = expression.getValue(context);
~~~

Expression holds the parsed structure; context holds runtime data. The two objects have different responsibilities and lifecycles.

Do not share a mutable EvaluationContext across concurrent requests if requests modify variables. Dedicated contexts prevent data from leaking across evaluations.

If sources change by policy version, cache Expression by ID/version and invalidate when a policy is replaced or revoked.

## 16. Error handling at the application layer

Not every SpEL error should be shown verbatim to end users.

You can categorize them:

| Scenario | Appropriate handling |
|---|---|
| Config has syntax error | Reject save/publish and point out position |
| Required variable or property missing | Report data/context error |
| Caller lacks permission for capability | Deny access |
| Conversion fails | Report invalid data error |
| Method throws exception | Record runtime failure and handle per contract |
| Expression returns false | Business result false, not an exception |
| Expression returns null when Boolean expected | Handle per policy; for access decisions, fail closed |

Do not catch every exception and return null, false, or a default value. Doing so can hide configuration errors and make business behavior unpredictable.

For access-control policies, only Boolean true should count as passing if that is the defined contract. Parse/evaluate errors, null, or other result types must be rejected or turned into appropriate operational errors.

## 17. Logging and diagnostic information

Internal logs can record:

- Policy ID and version.
- Error phase: parse, evaluate, or setValue.
- Exception class.
- Message code and position if available.
- Correlation ID.
- Context/parser configuration type.
- Mapped domain error code.

Do not log tokens, secrets, personal data, or the entire source expression if data policy prohibits it. Expressions may contain internal field names or sensitive configuration details.

Messages for configurators can state the error position and troubleshooting hints. Messages for regular clients should use stable application-defined error codes, without returning stack traces or internal structure.

## 18. Testing parse failures and evaluation failures

You should have separate tests for both phases.

JUnit example for parsing:

~~~java
@Test
void rejectsInvalidSyntax() {
    assertThatThrownBy(() ->
        parser.parseExpression("#amount *")
    ).isInstanceOf(SpelParseException.class);
}
~~~

JUnit example for evaluation:

~~~java
@Test
void validSyntaxCanFailWhenVariableIsMissing() {
    Expression expression =
        parser.parseExpression("#missingValue + 1");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    assertThatThrownBy(() ->
        expression.getValue(context)
    ).isInstanceOf(EvaluationException.class);
}
~~~

The test suite should include:

| Test case | Phase | Expected result |
|---|---|---|
| Valid arithmetic expression | Parse | Succeeds |
| Missing operand | Parse | SpelParseException |
| Unclosed string literal | Parse | SpelParseException |
| Template missing delimiter | Parse | ParseException |
| Unregistered variable | Evaluate | EvaluationException |
| Non-existent property | Evaluate | EvaluationException |
| Unprotected null receiver | Evaluate | Runtime evaluation failure |
| Unresolvable method | Evaluate | EvaluationException |
| Bean reference without resolver | Evaluate | Resolution failure |
| Invalid type conversion | Evaluate/setValue | Conversion failure |
| Expression returns false | Evaluate | Succeeds, result false |
| Expression returns null | Evaluate | Succeeds or null per expression; caller handles per contract |

Avoid asserting entire exception messages because formatting can change between versions. Prefer exception types, message codes when stable, and application behavior.

## 19. Common mistakes and how to handle them

| Symptom | Common cause | How to handle |
|---|---|---|
| Fixing brackets but error remains | Real error is in a token before the parser-reported position | Inspect source around position |
| Expression parses but fails to run | Missing variable or property in context | Inspect data and root object |
| Property name mistaken for variable | Forgot # prefix | Use #name for variables |
| Null-safe navigation still fails | Another receiver is unprotected | Place ?. at each potentially null layer |
| Method exists yet still fails | Overload, argument types, or resolver mismatch | Check signature and MethodResolver |
| Bean reference parses yet bean not found | BeanResolver unconfigured or wrong bean name | Check BeanFactory and resolver |
| Type reference parses yet class not found | TypeLocator disallows or cannot resolve class | Check TypeLocator |
| Conversion error | Incompatible source/target types | Check TypeConverter/ConversionService |
| Error only appears in production | Context, version, resolver, or data differs from tests | Record configuration and create equivalent fixture |
| Application masks errors | Broad catch returning default | Classify error, preserve cause, and handle per contract |

## 20. Practice exercises

1. Parse a valid arithmetic expression and evaluate the result.
2. Create an expression missing an operand and catch SpelParseException.
3. Parse #missingVariable successfully and then evaluate in a context without the variable.
4. Create an invalid property path and confirm the error occurs during evaluation.
5. Create a null root object and try safe navigation.
6. Create a method call with wrong argument types to check conversion/resolution.
7. Create an expression using @beanName in a context without a BeanResolver.
8. Create an expression using T(...) with a restricted TypeLocator.
9. Separate parse/evaluate into two try-catch blocks and map to distinct error codes.
10. Write a test confirming an expression returning false is not classified as an exception.
11. Write a regression test for a fixed runtime error.
12. Try logging position and message code without logging sensitive source or data.

## 21. Checklist before concluding a SpEL error

- [ ] Did the exception originate in parseExpression, getValue, or setValue?
- [ ] Is it SpelParseException or EvaluationException?
- [ ] Does the source have the right parser context and delimiters?
- [ ] Are parentheses/brackets, quotes, and operators valid per grammar?
- [ ] Is the variable registered in the exact EvaluationContext?
- [ ] Does the root object have the right type and state?
- [ ] Does the property path exist and is any layer null?
- [ ] Are the method signature and overload compatible?
- [ ] Are BeanResolver and TypeLocator configured when needed?
- [ ] Does TypeConverter support the source/target types?
- [ ] Has it been reproduced with a small fixture and equivalent data?
- [ ] Has a regression test been written for the cause?
- [ ] Is logging diagnostic enough without exposing sensitive data?
- [ ] Have overly broad catches returning defaults been avoided?

## 22. Conclusion

A parse failure occurs when the parser cannot turn the source into a valid Expression; an evaluation failure occurs afterward when the expression needs data, properties, methods, beans, types, or conversions that runtime does not supply or permit. SpelParseException usually points to a grammar issue; SpelEvaluationException and related EvaluationExceptions point to a runtime issue. Separate parsing from evaluation, inspect exception types and positions, verify the context and runtime data, and write separate tests for each phase. Clear classification ensures accurate error handling and avoids hiding issues behind default values.