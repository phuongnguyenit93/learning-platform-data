# Do Not Put Sensitive Data into the Context If the Expression Does Not Need It

## 1. EvaluationContext Can Supply Data to SpEL

Spring Expression Language (SpEL) evaluates expressions inside an environment called EvaluationContext. A context can supply a root object, variables, functions, and mechanisms for accessing properties, methods, types, or beans depending on configuration.

Example:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("orderTotal", 1200);
    context.setVariable("member", true);

    Expression expression = parser.parseExpression(
        "#member and #orderTotal >= 1000"
    );

    Boolean eligible =
        expression.getValue(context, Boolean.class);

The expression only needs two facts: orderTotal and member. Therefore the context only needs to contain those two values.

If the application also puts passwords, access tokens, private keys, session credentials, or unrelated personal information into the same context, that data does not help the expression perform its job and creates additional risk when the expression is evaluated or accessed unexpectedly.

Key principle: only supply the data that the expression genuinely needs to produce its result.

## 2. Variables Are Not a Secret Store

Variables in SpEL are registered with setVariable and referenced using the # symbol:

    context.setVariable("minimum", 1000);

    #minimum

Example with sensitive data:

    context.setVariable("apiToken", token);
    context.setVariable("password", password);
    context.setVariable("privateKey", privateKey);

These values remain plain data in EvaluationContext. SpEL does not automatically encrypt, mask, or classify them as secrets just because they were placed in variables.

If an expression can access the context and knows the variable name, it can reference the corresponding variable:

    #apiToken
    #password

Therefore, putting data into a variable should not be treated as a measure to protect secrets. Variables are merely a way to pass data into an expression.

If the expression does not need a token, password, or private key, do not register them in the context.

## 3. Pass Only the Minimal Facts

Suppose a rule needs to decide whether an order qualifies for free shipping.

Do not put entire objects containing lots of sensitive information into the context just so an expression can read a few fields:

    context.setVariable("customer", entireCustomerEntity);
    context.setVariable("order", entireOrderEntity);

These entities may contain emails, phone numbers, addresses, internal notes, payment details, or relationships to other objects.

Create narrow input data consisting only of the required values:

    context.setVariable("orderTotal", order.getTotal());
    context.setVariable("member", customer.isMember());
    context.setVariable("shippingRegion", order.getShippingRegion());

    Expression rule = parser.parseExpression(
        "#member and #orderTotal >= 1000 and #shippingRegion == 'VN'"
    );

The expression does not need to know passwords, tokens, or payment details to evaluate this rule.

A good way to organize this is to create a dedicated DTO or record for evaluation:

    public record ShippingFacts(
        BigDecimal orderTotal,
        boolean member,
        String shippingRegion
    ) {}

    ShippingFacts facts = new ShippingFacts(
        order.getTotal(),
        customer.isMember(),
        order.getShippingRegion()
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext(facts);

When using a root object, the expression can read:

    orderTotal >= 1000 and member and shippingRegion == 'VN'

A narrow DTO lets readers see the exact data the expression is allowed to use.

## 4. Distinguishing Root Object, Variables, and Bean References

Data can enter an expression through multiple paths:

| Provisioning Method | How Referenced | Example |
| --- | --- | --- |
| Root object | Direct property name | orderTotal |
| Variable | # prefix | #orderTotal |
| Bean reference | @ prefix, when BeanResolver is present | @pricingService |

Not only variables need to be controlled. The root object can also expose more properties and methods than the expression actually needs.

For example, if the root object is a large service or entity, the expression might access additional members that the original rule author did not intend to expose, depending on configured property accessors and method resolvers.

Similarly, if a BeanResolver is registered allowing references to many beans, the expression can access those beans using @beanName syntax.

Therefore, control all data sources and access permissions of the context:

- The root object should be a DTO or an object with a narrow data scope.
- Variables should only hold required facts.
- Functions should only perform permitted operations.
- BeanResolver should only be supplied when a trusted expression genuinely needs beans.
- PropertyAccessor and MethodResolver need to be configured according to intended use.

## 5. Do Not Embed Secrets Directly in the Expression String

Do not write tokens or passwords as literals in an expression:

    #apiClient.call('sk-live-sensitive-value')

Expression contents may be stored in configuration, databases, logs, traces, caches, or error messages depending on how the application manages them. Putting secrets into the string increases the number of places where they might accidentally be stored or displayed.

If an operation genuinely needs credentials, let a Java service take responsibility for retrieving credentials from a secret manager or the application's secret management mechanism. The expression should only decide a non-sensitive business condition or invoke a restricted API if the use case is controlled.

For example, instead of putting a token into the context:

    context.setVariable("apiToken", token);

perform authentication or API calls inside a controlled service, and then provide only the needed result:

    context.setVariable("authorized", authorizationResult.isAllowed());

    Boolean canContinue = parser
        .parseExpression("#authorized and #orderTotal <= #limit")
        .getValue(context, Boolean.class);

The expression only needs to know whether the authorized decision is true or false; it does not need to know the credentials that produced that decision.

## 6. Avoid Exposing the Entire ApplicationContext to Expressions

ApplicationContext is a broad-scoped object that can grant access to many beans and services of the application.

Do not set ApplicationContext as the root object or a variable merely so an expression can look up arbitrary data:

    context.setRootObject(applicationContext);

    context.setVariable("applicationContext", applicationContext);

This significantly expands the expression's access surface. Depending on accessor and resolver configurations, the expression could reach far more objects than the original business requirement.

If an expression needs a specific bean in a trusted flow, provide that exact bean via BeanResolver or supply a narrow wrapper with an allowed API.

If an expression only needs a few values, pass those values instead of passing the entire container.

## 7. Limiting Capabilities of EvaluationContext

StandardEvaluationContext provides many SpEL capabilities, including root object, variables, functions, property accessors, method resolvers, type locator, constructor resolvers, and bean resolver.

This is a flexible choice for application-controlled expressions. However, do not expose all of these capabilities by default to untrusted expressions.

SimpleEvaluationContext is designed for data binding and property-based expressions that require restricted capabilities. Depending on the builder and configuration, you can choose property access and certain suitable method invocation capabilities.

SimpleEvaluationContext does not provide the full feature set of StandardEvaluationContext; specifically, it does not support type references, constructors, and bean references.

Example of creating a read-only context for data binding:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

If you only need to read properties on a data object, a restricted context like this may fit better than a full context.

However, SimpleEvaluationContext is not an automatic guarantee of safety for every expression. Inspect exactly which property accessors and method resolvers are enabled, which objects are supplied, and where the expression comes from.

## 8. User-Provided Expressions Need Separate Controls

Risk increases when users can enter or edit SpEL strings themselves.

For example, an application allows users to create rules:

    #orderTotal >= 1000

If the context only holds orderTotal, the exposed data scope is quite narrow.

However, if the same expression engine is given a broad service object, beans, or methods with side effects, another expression could attempt to access capabilities beyond the intended goal.

Measures to apply:

- Prefer expressions controlled by the application and stored in trusted sources.
- If allowing users to create rules, support only an explicit set of syntax and features.
- Do not put credentials, tokens, private keys, or objects containing secrets into the context.
- Use read-only DTOs and restricted property accessors and method resolvers.
- Do not register BeanResolver or constructor resolvers if the use case does not require them.
- Do not allow expressions to invoke methods with side effects or arbitrary I/O.
- Validate input data types and value ranges before evaluation.

If business logic only needs a few comparisons or logical operators, consider a structured DSL or rule model instead of letting users enter general-purpose SpEL.

Do not rely on hiding variable names to protect data. Protective boundaries must be established by excluding secrets from the context and restricting access capabilities.

## 9. Isolating Contexts Between Requests

EvaluationContext can hold variables and state that change on each evaluation. If an application shares a mutable context across multiple requests, data from one request can be overwritten or observed in another if synchronization and lifecycle are not controlled.

For example, do not casually share a context and update variables per request:

    sharedContext.setVariable("customerId", customerId);
    sharedContext.setVariable("orderTotal", total);

If two requests run concurrently, they can overwrite each other's data.

A simpler approach is to create a dedicated context for each evaluation or each request:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customerId", customerId);
    context.setVariable("orderTotal", total);

    Boolean allowed =
        expression.getValue(context, Boolean.class);

Parsed Expressions can be retained for reuse if the source is fixed and trusted. Contexts containing request data should have their own lifecycle without sharing mutable state across requests.

If performance optimization is needed, separate immutable resolver/accessor configuration from per-request dynamic data and ensure that reuse pattern is concurrency-safe.

## 10. Do Not Log Context Contents or Secrets

Debugging expressions does not mean writing the entire context into logs.

Avoid:

    log.debug("SpEL context: {}", context);
    log.debug("Evaluation variables: {}", variables);

Depending on implementation, logging objects or maps may expose tokens, passwords, personal data, or internal information.

Log only minimal technical information:

- Controlled rule ID or expression name.
- Evaluation timestamp and processing duration.
- Success/failure outcome.
- Error type and expression position if free of sensitive data.
- Correlation ID for tracing the request.

If observing input values is necessary, log only non-sensitive or redacted fields. Do not put secrets in expression literals because expression contents can also appear in logs or error messages.

## 11. If an Expression Truly Needs Sensitive Information

Some business logic may need decisions based on sensitive data. Even then, raw secrets do not necessarily have to be placed into SpEL.

Prefer performing sensitive operations in a Java component with explicit privileges:

    boolean verified =
        credentialVerifier.verify(candidateCredential);

    context.setVariable("credentialVerified", verified);

    Boolean canProceed = parser
        .parseExpression("#credentialVerified and #accountEnabled")
        .getValue(context, Boolean.class);

The expression only receives a boolean result. Credentials are processed inside the verifier and do not need to appear in the context.

If providing a sensitive value to an expression is unavoidable, restrict it as follows:

- Only an application-controlled expression may be evaluated.
- The context exists only for the shortest scope necessary.
- Supply the value only for that single evaluation.
- Do not allow other expressions or other users to access the context.
- Do not log or serialize the context.
- Clear references to the data after completion if appropriate for the application's memory management.

Clearing references in Java does not guarantee a secret disappears immediately from JVM memory. For credentials requiring high protection, use proper secret management mechanisms and minimize the number of components receiving raw secrets.

## 12. Common Design Mistakes

| Design | Risk | Resolution |
| --- | --- | --- |
| Putting entire entities into context | Expression can read unnecessary fields and relationships | Use narrow DTOs |
| Putting passwords or tokens into variables | Expression can reference those values | Do not register secrets unless needed |
| Setting ApplicationContext as root | Expands access scope to container | Supply specific objects or beans |
| Providing BeanResolver to untrusted rules | Can open paths to unintended beans | Do not provide bean resolver unless needed |
| Allowing broad method invocation | Can call methods with side effects or I/O | Restrict MethodResolver and exposed APIs |
| Sharing mutable context across requests | Risk of data mixing across evaluations | Dedicated context per request |
| Logging entire context | Secrets can appear in logs and observability systems | Redact and log only needed metadata |
| Believing #variable is encrypted | Variables are just data in context | Design according to least privilege |

## 13. Checklist Before Evaluating an Expression

Before calling getValue, verify:

1. Does the expression genuinely need this data?
2. Does the root object contain sensitive fields or methods?
3. Do variables contain unnecessary tokens, passwords, private keys, or personal data?
4. Can raw secrets be replaced with a boolean outcome or pre-processed facts?
5. Are BeanResolver, ConstructorResolver, or method invocation required?
6. Does the expression come from an untrusted user source?
7. Is the context isolated across requests?
8. Could logs and error messages leak the expression or input data?
9. Can SimpleEvaluationContext or a more restricted rule model be used?
10. Do exposed objects match the exact scope of permissions the rule needs?

If the answer for an access permission is unnecessary, remove that permission from the context.

## 14. Key Points to Remember

- EvaluationContext is where root objects, variables, and access mechanisms are supplied to SpEL.
- Variables are registered with setVariable and referenced with #name.
- Variables are not automatically encrypted or hidden; they are not a secret store.
- Pass only the data needed by the expression; do not put entire entities or ApplicationContext into the context.
- Do not put passwords, tokens, or private keys into the context if the expression does not need them.
- Do not place secrets directly inside the expression string.
- Root object, BeanResolver, PropertyAccessor, and MethodResolver are also data access paths that must be controlled.
- SimpleEvaluationContext provides a more restricted feature set but still requires proper configuration.
- User-provided expressions must be strictly controlled; consider a restricted DSL if only a small rule set is needed.
- Create a dedicated context for each request's dynamic data and avoid sharing mutable state.
- Do not log the entire context or variable values; redact sensitive data.
- If logic needs secrets, process them in a component with explicit privileges and pass only the necessary outcome into the expression.

Design EvaluationContext following the principle of least privilege: each expression sees only the facts and operations needed for its task. Reducing data and access permissions up front is the clearest way to avoid unintended secret exposure.

## References

- Spring Framework Reference — Evaluation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — Variables: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html
- Spring Framework Reference — Security: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html
- Spring Framework Javadoc — SimpleEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html
