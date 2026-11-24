# Threats When Evaluating Expressions from Untrusted Data

## 1. Why Is Evaluating Untrusted SpEL Dangerous?

Spring Expression Language (SpEL) is an expression language capable of interacting deeply with Java objects. Depending on the EvaluationContext, an expression can read and write properties, invoke methods, instantiate objects via constructors, reference Spring beans, access collections, and perform type conversions.

Those capabilities are useful when expressions are configured by trusted developers or administrators. However, if users or external systems can control the expression content, they can cause the application to perform unintended actions.

Spring warns that evaluating SpEL from untrusted sources is inherently dangerous and should generally be avoided. StandardEvaluationContext provides the full feature set of the language and must never be used to evaluate expressions from untrusted sources. SimpleEvaluationContext restricts a subset of features, but only provides best-effort protection and is not a guaranteed-safe sandbox.

An expression source should only be considered trusted when provided by application developers or administrators responsible for configuration and operations. Expressions submitted by end users, customers, other tenants, or external systems must be treated as untrusted, even if they are stored in a database or configuration file.

## 2. Expression Injection and CWE-917

Expression Language Injection occurs when externally controlled data is inserted into an expression statement and then evaluated as code by the interpreter.

Dangerous design example:

    String source =
        "#customerName == '" + userInput + "'";

    Expression expression =
        parser.parseExpression(source);

If userInput contains quotes and SpEL syntax, the input content can alter the structure of the expression. The application has turned data into part of the executed program.

This is a class of vulnerability categorized as CWE-917: Improper Neutralization of Special Elements used in an Expression Language Statement.

You should not try to solve this simply by stripping a few special characters such as quotes, `#`, or parentheses. SpEL has many representations and syntaxes; a simple character filter easily misses other cases.

The best approach is not to concatenate untrusted data into the expression source. Keep the source fixed and pass data through variables.

## 3. Passing Data via Variables Instead of String Concatenation

If the goal is to compare a user-submitted value, parse a fixed expression and pass the value into the EvaluationContext.

Safer approach:

    Expression expression =
        parser.parseExpression(
            "#customerName == #expectedName"
        );

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setVariable("customerName", customerName);
    context.setVariable("expectedName", userInput);

    Boolean matches =
        expression.getValue(context, Boolean.class);

In this example, userInput is purely data. It is not parsed again as SpEL syntax.

Two situations need to be distinguished:

- Users provide values for an application-authored expression: pass them via variables or parameters of a structured API.
- Users are allowed to write the entire expression: this is a user-controlled programming language and requires designing a dedicated execution boundary.

There is no general-purpose escaping function that makes any untrusted SpEL expression safe. If the business requirement needs users to create their own rules, consider a restricted DSL or rule model that only supports predefined comparisons and operators.

## 4. Method Invocation and Executing Unintended Actions

With StandardEvaluationContext and default resolvers, SpEL can invoke methods on objects accessible to the expression.

Example expression:

    #accountService.disableAccount(#accountId)

If accountService is placed into the context or can be resolved through a bean resolver, the expression can trigger an operation that modifies account state.

Other methods can send emails, write data, delete files, call APIs, process payments, or modify permissions. When an expression can invoke them, whoever controls the expression can control application behavior within the scope of the exposed objects.

Do not place broadly privileged services into the root object, variables, or BeanResolver for untrusted expressions. If a rule only needs to know whether an account is permitted to proceed, perform the authorization check in a trusted service and pass the boolean result into the context.

Merely allowing a few named functions is also insufficient if the root object or other variables still expose dangerous methods through the method invocation mechanism.

## 5. Class, Constructor, and Bean Access

StandardEvaluationContext can support many extended features such as:

- Type references using `T(...)`.
- Object instantiation using `new`.
- Static method invocation.
- Bean references via BeanResolver.
- Method invocation and property access on resolved objects.

For example, the following expressions illustrate capabilities that must be controlled:

    T(java.lang.System).getProperty('user.name')

    new java.util.Date()

    @pricingService.calculate(#amount)

The first expression can read a system property, the second instantiates a new object, and the third invokes a method on a resolved bean.

Do not grant a TypeLocator, ConstructorResolver, or BeanResolver to untrusted expressions if the business logic does not need them. In particular, do not expose the entire ApplicationContext or administrative services to the expression scope just for lookup convenience.

SimpleEvaluationContext excludes type references, constructor invocation, and bean references. However, objects and methods may still be accessible through the root object, variables, property accessors, method resolvers, and configured functions.

## 6. Data Exposure Through the Root Object and Variables

An expression can read any property permitted by the active accessors on objects it can reach.

If the root object is a large entity or a service, the expression can traverse nested properties to reach information beyond the intended scope.

Examples:

    #customer.profile.email

    #customer.paymentDetails.accountNumber

    #configuration.internalEndpoint

Even when an expression only needs to check a simple condition, putting the entire entity into the context can inadvertently expose much more data.

Do not provide passwords, access tokens, private keys, session credentials, or unnecessary personal information in variables. A variable is not a secret store; it is simply data that an expression can reference with `#`.

Create a dedicated DTO or record for evaluation that contains only the required facts:

    public record AccountFacts(
        boolean active,
        boolean verified,
        String region
    ) {}

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setRootObject(
        new AccountFacts(true, true, "VN")
    );

The expression only sees active, verified, and region. It has no need to access entities, repositories, credentials, or internal services.

## 7. Property Getters Can Also Cause Side Effects

A dangerous misconception is assuming that a read-only expression always only reads data and cannot modify state.

SpEL can access properties through methods shaped like accessors: public methods with no parameters that return a value. This shape does not prove that the method is truly read-only.

For example, the following methods can look like property accessors:

    file.delete()
    queue.poll()
    counter.incrementAndGet()

When the corresponding object is exposed and the accessor permits it, an expression can access them as property-like operations. These methods mutate state even though the syntax looks like reading a property.

Spring explicitly notes that ReflectivePropertyAccessor and DataBindingPropertyAccessor cannot automatically determine whether an accessor-shaped method has side effects.

Therefore, read-only in SimpleEvaluationContext only controls property assignment. It does not prove that getters or accessor methods are pure and side-effect-free.

Review every zero-argument value-returning method on exposed objects. Only place objects with safe, narrowly scoped read APIs into the context.

## 8. Transitive Accessibility Through Nested Objects

Restricting the root object is not enough if its properties return a broadly privileged object.

Example:

    #facts.customer.address.city

If facts.customer returns a large entity, the expression can continue navigating into other properties of that entity. Similarly, an object retrieved via an indexer or a variable can open up a new branch of access.

Inspect the entire object graph reachable by the expression:

- The root object and returned properties.
- Objects inside Lists, arrays, and Maps.
- Variables holding objects.
- Return values from methods or functions.
- Beans resolved via BeanResolver.
- Objects returned from a custom PropertyAccessor.

A DTO that contains only a few fields but returns an entity or service through a getter can still widen the access scope. Boundaries must be enforced at every level, not just on the first object.

Prefer dedicated, immutable data types that expose only the necessary values. Avoid getters that return infrastructure objects, repositories, connections, file handles, or broadly privileged services.

## 9. Property Writing and State Modification

SpEL supports assignment and `Expression.setValue` when the EvaluationContext and PropertyAccessor allow writes.

Example:

    #account.enabled = false

    Expression expression =
        parser.parseExpression("enabled");

    expression.setValue(context, account, false);

If an untrusted expression can write properties, it can alter object state and affect other requests or users sharing that object.

Some countermeasures:

- Use immutable DTOs or a read-only context when only evaluating conditions.
- Do not expose entities managed by a persistence context if the rule does not need to write.
- Do not grant a PropertyAccessor with broad write permissions.
- Disallow assignment if the business logic does not require it.
- Perform state changes through services with authorization, validation, and transactions.
- Do not consider using a read-only SimpleEvaluationContext sufficient if accessor-shaped methods can still mutate state.

If an expression must update data, explicitly define which properties are writable and validate values before applying them.

## 10. Denial of Service and Resource Consumption

Untrusted expressions can consume CPU, memory, or trigger many repeated operations.

Common causes:

- Overly long or deeply nested expressions.
- Selection/projection iterating over large collections.
- Methods invoked repeatedly on each element that perform I/O.
- Complex regexes or patterns with expensive backtracking.
- Arithmetic operations with very large values.
- Functions or methods that allocate overly large collections or objects.
- Many expressions evaluated concurrently without limits.

Example:

    #orders.?[customer.isEligible()].![total]

If orders contains a very large number of elements and isEligible executes a database query, a short expression can cause a large number of queries.

Input limits and per-evaluation cost matter more than how short an expression looks at a glance.

## 11. SpEL Parser and Operation Limits

Spring provides several configurable limits to reduce the risk of expressions consuming excessive resources. According to current Spring documentation, the defaults include:

| Limit | Documented Default | Purpose |
| --- | ---: | --- |
| Maximum expression length | 10,000 characters | Limits overly long expression sources |
| Maximum operations | 10,000 operations | Limits the number of operations during evaluation |
| Maximum BigDecimal/BigInteger power result | 1,000,000 bits | Limits the result size of exponentiation operations |

Lower values can be configured according to workload:

    SpelParserConfiguration configuration =
        SpelParserConfiguration.builder()
            .maximumExpressionLength(5_000)
            .maximumOperations(1_000)
            .maximumBigPowerBits(100_000)
            .build();

    SpelExpressionParser parser =
        new SpelExpressionParser(configuration);

The numbers above are the defaults described in current documentation and should not be assumed identical across all versions or configurations. Check the Spring version in use and the actual parser configuration.

These limits help bound certain kinds of cost. They do not replace timeouts, collection limits, method controls, concurrency limits, or secure context design. An exposed method can still block or perform I/O even if the expression stays below the operation limit.

## 12. Separating Expression Parsing from Input Data

If the user only provides a value, do not parse that value as an expression.

For example, when filtering by status, use a fixed expression:

    #order.status == #expectedStatus

Pass expectedStatus into the context:

    context.setVariable(
        "expectedStatus",
        userSuppliedStatus
    );

If the user is allowed to choose a field from an allowed list, map that selection to an application-defined property path:

    Map<String, Expression> allowedRules = Map.of(
        "active", parser.parseExpression("active"),
        "verified", parser.parseExpression("verified")
    );

    Expression selected =
        allowedRules.get(userSelectedRule);

Do not take userSelectedRule directly and concatenate it into the expression source.

If users must write rules themselves, build a restricted DSL or a declarative schema-backed data structure, then translate that structure into a controlled expression. Simply checking a few substrings or blacklisting tokens does not make a parser secure.

## 13. SimpleEvaluationContext Is Not a Sandbox

SimpleEvaluationContext is designed for cases that need a subset of SpEL features, such as data binding or property-based filtering.

You can start with read-only data binding:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

This configuration does not support type references, constructor invocation, or bean references like StandardEvaluationContext. It also does not enable full method resolution.

However, Spring emphasizes that SimpleEvaluationContext's restrictions are only best-effort and do not guarantee safe evaluation. Any property, method, or function reachable from the root object, accessors, resolvers, variables, or functions still needs to be controlled.

Read-only data binding also does not verify that getters are free of side effects. Therefore, input objects must be designed safely from the start.

## 14. Do Not Reuse an Expression Across Different Privilege Levels

An important security detail relates to internal caching inside an Expression's AST.

For performance, nodes of a parsed Expression may cache the PropertyAccessor, IndexAccessor, MethodExecutor, or ConstructorExecutor used during a previous evaluation.

Therefore, you must not evaluate the same Expression instance first with a broadly privileged context and then reuse it with a more restricted context, expecting the new restrictions to always apply.

Design example to avoid:

    Expression shared =
        parser.parseExpression("customer.profile");

    shared.getValue(
        privilegedContext,
        privilegedRoot
    );

    // Do not reuse shared with a context that has a different security policy.
    shared.getValue(
        restrictedContext,
        restrictedRoot
    );

Spring considers reusing an Expression across contexts with different security implications to be an unsupported usage pattern.

If the same expression source needs to be evaluated under multiple security profiles, parse it into separate Expression instances for each profile and do not transfer an instance used in a broadly privileged context to a lower-privilege context.

It is best to keep resolver/accessor configuration stable throughout the expression lifecycle. Do not change a context's security policy after an expression has been evaluated and assume old caches have no effect.

## 15. Isolating EvaluationContext Across Requests and Tenants

An EvaluationContext can hold a root object, variables, functions, and resolvers. If a mutable context is shared across multiple requests, data or privileges from one request can affect another.

Dangerous example:

    sharedContext.setVariable("tenantId", tenantId);
    sharedContext.setVariable("account", account);

Two concurrent requests can overwrite variables or mistakenly use another tenant's objects if state is shared improperly.

Create a dedicated context per request or evaluation when the context contains dynamic data:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setRootObject(accountFacts);

A parsed Expression can be reused across contexts with equivalent security configurations according to Spring's guidance. However, do not share an Expression instance across contexts with different privilege levels.

For multi-tenant systems, identify the tenant before creating the root object, place only data belonging to that tenant into the context, and do not use a global mutable context to hold request data.

## 16. Do Not Arbitrarily Log Expressions and Contexts

Expression sources, variable values, and evaluation errors can contain sensitive information.

Avoid logging the entire context:

    log.debug("Evaluation context: {}", context);
    log.debug("Rule variables: {}", variables);

Do not log passwords, tokens, private keys, personal data, or user-entered expression content unless there is a clear need and appropriate safeguards are in place.

Log minimal metadata instead:

- Rule ID or rule version.
- Evaluation timestamp and duration.
- Success/failure outcome.
- Sanitized error type and error location.
- Correlation ID for request tracing.
- Tenant or actor ID according to the application's logging policy.

If input must be logged for investigation, redact or pseudonymize sensitive fields and restrict log access and retention.

## 17. Distinguishing Expression Injection from XSS and SQL Injection

Expression injection is a vulnerability where untrusted data is interpreted as executable syntax by an expression interpreter.

It differs from:

- SQL injection: data alters the structure of a SQL query.
- Command injection: data alters the command passed to a shell or process.
- Cross-site scripting: data is rendered as script code in a browser.

A SpEL value returning a String is not automatically HTML-escaped. If the result is placed into a web page, the application must still perform context-appropriate output encoding for HTML, attributes, JavaScript, or URLs.

Similarly, using SpEL does not replace prepared statements when querying a database. Use parameterized APIs for SQL and safe APIs for each interpreter.

A system can suffer from multiple injection types simultaneously if the same untrusted data is passed through multiple interpreters.

## 18. Expression Evaluation Protection Checklist

Before allowing an expression to be evaluated, check:

1. Who controls the expression source: developer, administrator, end user, or external system?
2. Can evaluating user-supplied expressions be avoided altogether?
3. If only data is needed, is it passed via variables instead of string concatenation?
4. Can general-purpose SpEL be replaced with a schema-backed DSL or rule model?
5. Does the context use SimpleEvaluationContext with the minimum required features?
6. Is the root object a narrow, immutable DTO containing only necessary data?
7. Do all nested objects and index results expose safe APIs?
8. Do any getter/accessor-shaped methods have side effects?
9. Are any functions, methods, beans, types, or constructors exposed too broadly?
10. Are property assignments or state-mutating methods permitted?
11. Does the parser enforce limits on length, operations, and arithmetic size?
12. Do collections and inputs have size, timeout, and concurrency limits?
13. Is an Expression instance reused across contexts with different privilege levels?
14. Is a mutable context shared across requests or tenants?
15. Could logs or outputs leak data or introduce XSS?
16. Is Spring Framework on a version up to date with security fixes?

If you cannot clearly answer whether an access privilege is needed, remove that privilege from the context before putting the expression into use.

## 19. Key Takeaways

- Evaluating SpEL from untrusted sources is inherently dangerous; avoid it whenever possible.
- StandardEvaluationContext must not be used to evaluate untrusted expressions.
- SimpleEvaluationContext only restricts features on a best-effort basis and is not a sandbox.
- Do not concatenate user data into expression sources; use variables or parameterized APIs.
- Expressions can invoke methods, instantiate objects, read/write properties, and reference beans according to the context's privileges.
- Do not expose entities, ApplicationContext, services, or objects containing secrets if the rule does not need them.
- Accessor-shaped getters can still delete files, mutate queues, or update counters.
- Inspect the entire object graph, including nested objects, collections, variables, and function results.
- Use dedicated, immutable DTOs with a narrow data scope.
- Limit expression length, operation count, numeric and collection sizes, and control timeouts/concurrency.
- Do not reuse the same parsed Expression instance across contexts with different security implications.
- Isolate mutable contexts per request and per tenant.
- Do not log full expressions, contexts, or secrets.
- Output encoding, SQL parameterization, and command safety remain separate responsibilities.

Treat EvaluationContext as a set of permissions granted to an expression. An expression should only see the data and operations needed for its task. Designing a narrow context, passing data as data, limiting resources, and keeping expressions out of user control are the most important layers of defense.

## References

- Spring Framework Reference — Evaluation and Security Considerations: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — SpEL Parser Configuration and Compiler: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/expressions.html
- MITRE CWE-917 — Expression Language Injection: https://cwe.mitre.org/data/definitions/917.html
- OWASP — Expression Language Injection: https://owasp.org/www-community/vulnerabilities/Expression_Language_Injection
- OWASP — Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html
