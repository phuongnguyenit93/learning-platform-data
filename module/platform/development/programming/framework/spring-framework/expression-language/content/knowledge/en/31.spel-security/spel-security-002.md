# Distinguishing Developer-Authored and User-Supplied SpEL Expressions

Spring Expression Language (SpEL) is an expression language that can read properties, perform operations, invoke methods, and access components provided in an EvaluationContext. Therefore, a SpEL expression is not merely a text string: when evaluated, it can execute behavior on objects that the context permits access to.

Two expression sources must be clearly distinguished:

- **Developer-authored expressions** are part of source code or configuration that is controlled, reviewed, and released together with the application.
- **User-supplied expressions** come from requests, admin UIs, externally provided configuration files, or an equivalent untrusted source. They must be treated as externally supplied programs.

This distinction determines how to choose an EvaluationContext, what data is placed into the root object, whether method invocation or bean referencing is allowed, and how input is validated. This article focuses on trust boundaries and safe design patterns when an application needs to use SpEL for both cases.

## 1. Why Does the Origin of an Expression Matter?

The same expression can be safe in one context and dangerous in another. For example:

~~~text
account.active and account.balance >= 100
~~~

If the expression is authored by a developer and evaluated against a small DTO containing only the necessary data, its behavior is predictable.

If users are free to submit expressions, they can change which properties are read, add method calls, or use other capabilities provided by the EvaluationContext. When the context has broad access privileges, an expression can read data beyond its original purpose or trigger unintended behavior.

Therefore, before evaluating SpEL, three questions must be answered:

1. Who controls the expression content?
2. Which objects and behaviors is the expression allowed to access?
3. What is the result used for, especially whether it affects authorization or mutates state?

Safety should not be judged merely by whether the expression string looks simple or contains only a few comparisons.

## 2. Developer-Authored Expressions

Developer-authored expressions typically reside in source code, annotations, XML bean definitions, or configurations controlled through the release process.

Example in Java code:

~~~java
@Value("#{T(java.lang.Math).max(10, 20)}")
private int batchSize;
~~~

Example in Spring Security:

~~~java
@PreAuthorize("@documentAuthorization.canRead(authentication, #documentId)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId);
}
~~~

In these examples, the developer decides the expression, the data types accessed, and the beans or methods invoked. The expression can be reviewed as part of the source code.

However, a developer-authored expression does not mean all data passed into it is trustworthy. Values from HTTP requests, account names, document IDs, or form contents are still external data. They must be passed as data and validated according to business rules.

A controlled expression can handle untrusted data more safely when data is passed through variables or a well-structured root object, rather than concatenated directly into the expression string.

## 3. User-Supplied Expressions

User-supplied expressions are content that the application does not control ahead of runtime. Examples:

- Admin users creating custom data-filtering conditions.
- Customers entering calculation rules in a configuration screen.
- Systems receiving expressions from external files or services.
- Users being able to edit a configuration field stored in a database, which the application later evaluates with SpEL.

A string stored in a database is still untrusted input if users or external systems can modify it.

When evaluating an external expression, the submitter is providing executable logic. This string should not be treated as an ordinary data value, nor should it be assumed that parsing successfully means the expression is safe.

If the business logic only needs users to choose a condition, such as status equals ACTIVE or balance greater than a threshold, consider a strongly typed rule structure instead of allowing arbitrary SpEL input.

## 4. Risks of Concatenating User Data into Expressions

A common design mistake is concatenating input directly into a SpEL string:

~~~java
String spelText =
        "'" + userInput + "' == 'admin'";

Expression expression =
        parser.parseExpression(spelText);

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

This code turns user data into part of the expression syntax. If the input contains quotes or operators, it can alter the structure of the expression instead of being treated merely as data.

This is a form of expression injection. Removing a few characters with `replace` or regex is usually not enough to ensure safety, because SpEL has many syntactic constructs and value representations.

The proper approach is to keep a fixed developer-authored expression and pass input via variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("input", userInput);

Expression expression =
        parser.parseExpression("#input == 'admin'");

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

In this example, userInput is the value of the `input` variable. That content is not re-parsed as a SpEL snippet.

Key principle: **user data must enter an expression as bound data, not by string concatenation into the expression code**.

## 5. Parsing an Expression Is Not the Same as Evaluating It

SpEL typically has two phases:

1. The parser parses the string and creates an Expression object.
2. The application calls `getValue()` or another evaluation operation to execute the expression within an EvaluationContext.

Example:

~~~java
Expression expression =
        parser.parseExpression("age >= 18");

Boolean eligible =
        expression.getValue(context, source, Boolean.class);
~~~

`parseExpression()` processes syntax and may throw an error if the expression is invalid. `getValue()` evaluates the expression against the data and access capabilities provided by the context.

Successful parsing does not prove an expression is safe. A syntactically valid expression can still invoke methods, read sensitive properties, or perform inappropriate actions if the context allows it.

Both the expression content and the evaluation environment must be controlled. Successful parsing should not be used as a security validation mechanism.

## 6. EvaluationContext Determines Expression Privileges

EvaluationContext provides the environment SpEL uses during evaluation. Key components can include:

- The root object and variables.
- PropertyAccessor for reading or writing properties.
- MethodResolver for finding callable methods.
- BeanResolver for referencing beans with `@beanName` syntax.
- TypeLocator for resolving `T(...)` type references.
- TypeConverter for converting values.
- Functions registered in the context.

StandardEvaluationContext has broad capabilities and is generally suitable for developer-controlled expressions. Providing a broadly privileged StandardEvaluationContext to a user-supplied expression allows users to reach capabilities the application did not intend to offer.

For example, the following syntax illustrates different capability groups:

~~~text
name
#minimumAge
#normalize(name)
@pricingService.defaultCurrency
T(java.lang.Math).max(10, 20)
~~~

These respectively illustrate properties, variables, functions, bean references, and type references. Not every application needs to open all of these capabilities to an expression.

Configure the context according to its exact purpose. Do not use a full-privilege context simply because it is convenient for both internal and external expressions.

## 7. Using SimpleEvaluationContext for Restricted Cases

SimpleEvaluationContext is designed to provide a more restricted subset of SpEL features than StandardEvaluationContext. The application must explicitly select the appropriate property access mechanism and method invocation capability.

Read-only data binding example:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression =
        parser.parseExpression("active and age >= 18");

Boolean result = expression.getValue(
        context,
        accountView,
        Boolean.class
);
~~~

This configuration is suitable when an expression needs to read properties from a data object. It does not provide full StandardEvaluationContext capabilities such as type references, constructor invocation, and bean references. Method invocation is also not enabled by default in this read-only data binding configuration.

SimpleEvaluationContext can reduce the access surface, but it is not an absolute sandbox for every kind of expression. Getters can still execute Java code, nested objects can still contain sensitive data, and large collections can still make traversal resource-intensive.

When dealing with user-supplied expressions:

- Provide only a small root object containing strictly allowed properties.
- Prefer read-only property access.
- Do not add a bean resolver or type access unless required by business logic.
- Do not enable method invocation arbitrarily.
- Verify the limits of the builders and accessors used in the specific Spring version.

If an even narrower set of operations is needed, design a custom DSL or rule model instead of exposing unrestricted SpEL.

## 8. Designing the Root Object Under the Principle of Least Privilege

The root object is the starting point for an expression to access data. Putting entire entities or large services into the context can expose far more properties and behaviors than necessary.

Do not directly provide objects that can lead to:

- The entire ApplicationContext or BeanFactory.
- Entities with many relationships and internal fields.
- Requests/sessions containing sensitive information.
- Services with mutating methods or external system calls.
- Objects containing tokens, credentials, or secrets.

Instead, create a DTO containing only the required fields:

~~~java
public class AccountRuleView {
    private final String status;
    private final int age;
    private final BigDecimal balance;

    public AccountRuleView(
            String status,
            int age,
            BigDecimal balance) {
        this.status = status;
        this.age = age;
        this.balance = balance;
    }

    public String getStatus() {
        return status;
    }

    public int getAge() {
        return age;
    }

    public BigDecimal getBalance() {
        return balance;
    }
}
~~~

Evaluating an expression on the DTO:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression = parser.parseExpression(
        "status == 'ACTIVE' and age >= 18 and balance > 0"
);

Boolean allowed = expression.getValue(
        context,
        accountRuleView,
        Boolean.class
);
~~~

This DTO exposes only status, age, and balance. The expression has no knowledge of repositories, services, entity graphs, or other account fields.

Least privilege applies to the root object, returned collections, and registered accessors alike.

## 9. Separating User-Selected Conditions from Expression Code

If users only need to build simple rules, you can provide a form or typed data structure:

~~~java
public enum RuleField {
    STATUS,
    AGE,
    BALANCE
}

public enum RuleOperator {
    EQUALS,
    GREATER_THAN,
    LESS_THAN
}

public class UserRule {
    private RuleField field;
    private RuleOperator operator;
    private String value;
}
~~~

The application validates each field and operator against an allowlist, then performs the comparison itself on normalized data.

For example, allow only:

- STATUS with EQUALS.
- AGE with GREATER_THAN or LESS_THAN.
- BALANCE with GREATER_THAN or LESS_THAN.

This approach lets users choose conditions without supplying arbitrary executable syntax. It also makes it easier to type-check, limit rule counts, store versions, and render configurations reliably.

If an expression language is genuinely needed, you can build a small DSL supporting only the required business properties and operators. Do not assume that filtering a few strings with regex turns the entire SpEL language into a safe DSL.

## 10. Validating User-Supplied Expressions

If the application must accept SpEL from external sources, clearly define the grammar and allowed capabilities before deploying to production.

A control workflow can include:

1. Limiting expression length and input data size.
2. Accepting only properties on a business allowlist.
3. Allowing only necessary operators and constructs.
4. Using an EvaluationContext with minimal privileges.
5. Not providing bean references, type references, or constructor invocation without a clear reason.
6. Not enabling method invocation if the expression only needs to read properties and compute values.
7. Validating the result type per contract, e.g., a rule must return a Boolean.
8. Testing with malformed syntax, null, boundary data, and large collections.
9. Limiting the number of stored, parsed, and evaluated expressions per user or tenant.

A parser can catch syntax errors, but parsing does not replace policy checks. If expression structure must be inspected, use an application-controlled grammar or rule model; avoid relying on unsupported internal AST classes as a stable API.

## 11. Risks from Method Invocation and Getters

Property access in Java typically goes through getters. Getters are Java code and can theoretically do more than return a field.

Example of a getter unsuitable for expressions:

~~~java
public BigDecimal getBalance() {
    auditService.writeAccessLog();
    return accountRepository.calculateCurrentBalance(id);
}
~~~

If the expression is evaluated multiple times, the getter can cause repeated queries or side effects. For user-supplied expressions, letting users choose properties with complex getters also makes execution cost harder to predict.

Similarly, method invocation can trigger state-changing behavior or external service calls.

Principles:

- Getters on rule DTOs should be simple and free of side effects.
- Do not place services with write operations on the root object.
- Enable method invocation only when truly necessary and restrict which methods can be called.
- Do not treat the `#` prefix or the use of SimpleEvaluationContext as a guarantee that all methods are safe.

## 12. Protecting Data and Access Rights

An expression can read any data exposed by the root object and accessors. If the source data contains emails, phone numbers, tokens, financial details, or another tenant's data, the expression can produce results containing that information.

Prepare data strictly within the scope the user is authorized to view before evaluating the expression. Do not rely on expressions to replace data access control checks.

For example, before evaluating a rule for a customer:

1. Authenticate the caller.
2. Verify tenant and object-level access permissions.
3. Load only the records the caller is authorized to view.
4. Build a DTO containing only the fields needed for the rule.
5. Evaluate the expression in a restricted context.
6. Verify the type and meaning of the result.

An expression returning true does not by itself prove the caller has permission to access the record. Authorization decisions must remain within the application's controlled security logic.

## 13. Resources, Execution Time, and Caching

User-supplied expressions can consume excessive resources even without calling dangerous beans or methods. For example, an expression can iterate over large collections, perform multiple nested projections/selections, or use the regex operator on long strings.

You should control:

- Expression length.
- Sizes of strings and collections placed into the context.
- Number of rules allowed to be stored per user.
- Evaluation frequency and concurrency levels.
- Which getters and operators are permitted.
- Number of distinct expressions kept in cache.

Do not assume SpEL itself provides a safe execution timeout for every expression. If a method can run for a long time, setting a timeout at the caller layer does not necessarily stop the code executing inside. A better approach is to prevent untrusted expressions from calling operations with unbounded execution time.

If caching Expressions, use a cache with bounded capacity and an appropriate eviction policy. Do not use an unbounded cache keyed by arbitrary user-submitted strings, as the number of distinct expressions can grow continuously.

## 14. Error Handling and Logging

External expressions can have syntax errors, access non-existent properties, produce results of the wrong type, or throw exceptions during evaluation.

Distinguish between:

- Parse exception: invalid expression syntax.
- Evaluation exception: error while evaluating a property, method, or operation.
- Conversion error: result cannot be converted to the target type.
- Validation error: expression is syntactically valid but violates application policy.

Do not return raw stack traces or internal details to end users. You can return a brief validation message while logging a correlation error code on the server side.

When logging, avoid storing the expression if it may contain personal data, secrets, or sensitive user input. If investigation is needed, log the rule identifier, creator, timestamp, version, and error type according to the application's data policy.

## 15. Example: Fixed Expression, Variable Data

This example illustrates how a developer keeps the expression fixed and passes user data through variables.

~~~java
public class AccountView {
    private final String status;
    private final int age;

    public AccountView(String status, int age) {
        this.status = status;
        this.age = age;
    }

    public String getStatus() {
        return status;
    }

    public int getAge() {
        return age;
    }
}

String requestedStatus = request.getParameter("status");

AccountView source = new AccountView(
        account.getStatus(),
        account.getAge()
);

StandardEvaluationContext context =
        new StandardEvaluationContext(source);

context.setVariable("requestedStatus", requestedStatus);

Expression expression = parser.parseExpression(
        "status == #requestedStatus and age >= 18"
);

Boolean matches = expression.getValue(
        context,
        Boolean.class
);
~~~

The expression is a developer-authored constant. `requestedStatus` is data from the request bound into a variable, so its content never becomes SpEL syntax.

In a real application, you must still validate `requestedStatus` against the set of valid statuses and check account access permissions before creating the source object.

## 16. Example: Evaluating an External Rule with a Restricted Context

If the business requirement truly demands user-entered rules, provide minimal data and use a read-only context:

~~~java
AccountRuleView source = new AccountRuleView(
        "ACTIVE",
        25,
        new BigDecimal("1500.00")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

String userExpression =
        "status == 'ACTIVE' and age >= 18 and balance > 0";

Expression expression =
        parser.parseExpression(userExpression);

Object result = expression.getValue(context, source);

if (!(result instanceof Boolean)) {
    throw new IllegalArgumentException(
            "Rule expression must return a Boolean"
    );
}

boolean matches = (Boolean) result;
~~~

The example uses a simple expression that only reads properties and performs comparisons. In a real application, you must also add a property/operator allowlist policy, size limits, permission validation, and tests for accepted expressions.

Do not extend this example into an endpoint that accepts arbitrary SpEL without restrictions. SimpleEvaluationContext reduces available features, but application policy must still define which expressions are accepted.

## 17. Common Mistakes

| Mistake | Cause | Remediation |
|---|---|---|
| Concatenating input into a SpEL string | Data can alter the expression syntax. | Use variables or a root object to pass data. |
| Assuming successful parsing means safe | Parsing only confirms the syntax can be parsed. | Control context privileges and expression policies. |
| Using a broad StandardEvaluationContext for external expressions | The context can expose many access capabilities. | Use a restricted context and minimal root object. |
| Exposing entire entities or services | Expressions can see unnecessary data and behaviors. | Use DTOs/read models with a property allowlist. |
| Enabling unrestricted method invocation | Methods can mutate state or call external systems. | Disable method invocation if unneeded; restrict resolvers if required. |
| Relying on regex to filter SpEL syntax | The grammar has many representations and nesting forms. | Use a typed DSL/rule model or explicit grammar control. |
| Using an expression as the sole authorization decision | Expression results do not replace data access checks. | Authenticate the caller and verify data scope before evaluation. |
| Not limiting collection or expression size | Expressions can consume excessive CPU and memory. | Limit length, data size, frequency, and rule count. |
| Caching all expressions unboundedly | Users can generate a huge number of keys. | Use a bounded cache or do not cache external expressions. |
| Returning stack traces to users | Leaks class names, structure, and internal details. | Return a short validation error and log safely on the server. |

## 18. Practical Guidelines

1. Classify expressions by origin and trust level before evaluation.
2. Keep developer-authored expressions in source code or controlled configuration.
3. Do not concatenate user data directly into SpEL strings.
4. Pass input through variables or strongly typed DTOs.
5. Provide only the necessary root object and properties.
6. Use SimpleEvaluationContext with read-only data binding when the problem only requires reading properties.
7. Do not grant bean references, type access, constructor invocation, or method invocation if not needed.
8. Use an allowlisted DSL/rule model when users need to define custom conditions.
9. Verify data access permissions independently of expression results.
10. Limit size, count, frequency, and resources when processing external expressions.
11. Handle parse, evaluation, conversion, and validation errors separately.
12. Do not treat successful parsing or a read-only context as an absolute security sandbox.

## 19. Summary

- Developer-authored expressions are controlled in source code or configuration; user-supplied expressions must be treated as untrusted programs.
- SpEL can read properties and execute methods depending on the capabilities provided by EvaluationContext.
- Concatenating input into an expression can cause expression injection.
- Keep expressions fixed and pass user data through variables or the root object.
- StandardEvaluationContext has broad capabilities; do not use a broadly privileged context for external expressions.
- SimpleEvaluationContext restricts features and fits certain read-only data binding cases, but is not an absolute sandbox.
- Small root objects and read-only DTOs help limit the data an expression can see.
- Successful parsing does not prove an expression is safe.
- Use a typed DSL/rule model when users only need to select business conditions.
- Control methods, getters, collection sizes, expression sizes, caches, and evaluation frequency.
- Authorization decisions and data access rights must be controlled independently of expressions.
