# Do Not Treat Successful Parsing as Proof of Safety in SpEL

Spring Expression Language (SpEL) separates syntax parsing from expression evaluation. `SpelExpressionParser.parseExpression(...)` checks and creates an Expression object from an input string. That call does not prove the expression is allowed to access data, invoke methods, or modify state at runtime.

A syntactically valid expression can still call sensitive beans, read out-of-scope properties, perform assignments, or cause side effects if the EvaluationContext grants the corresponding capabilities. Therefore, **successful parsing only proves the expression conforms to syntax accepted by the parser; it is neither an authorization check, a business validation check, nor a security sandbox**.

## 1. Distinguishing Parse and Evaluate

Two basic steps:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("#order.total > 100");

    Boolean allowed = expression.getValue(context, Boolean.class);

`parseExpression` parses the string and creates an Expression. `getValue` is what evaluates the expression within a specific EvaluationContext, using the root object, variables, property accessors, method resolvers, bean resolver, and other services provided by the context.

If the string has invalid syntax, an error occurs during parsing. If the syntax is valid but a variable, property, bean, or method does not exist, the error may only appear during evaluation. Even if all components exist, the expression can still perform an action that application policy forbids.

An expression can be parsed without executing it yet:

    Expression expression =
            parser.parseExpression("@orderService.load(#orderId)");

This snippet has not called `load` yet. The method can only be invoked when the expression is evaluated with a context capable of resolving the bean and calling the matching method.

## 2. Successful Parsing Does Not Mean the Expression Is Permitted to Run

The parser checks the syntax of the language. It does not know whether the current user has permission to read the order, which beans are allowed to be accessed in the use case, or whether a method can write to a database or send messages.

For example, the following expressions are all syntactically valid:

    #order.total > 100

    #order.status = 'APPROVED'

    @orderPolicy.canApprove(#order)

They have different meanings and execution capabilities:

- The first expression only compares values if the context allows reading properties.
- The second expression is an assignment; if the context has a suitable write accessor, it can mutate the object.
- The third expression requires a BeanResolver to look up the bean and a method resolver to invoke a method on that bean.

The parser does not decide for itself which expressions fit the use case. Whether evaluation is permitted must be controlled by the application through the context, policies, and business authorization checks.

## 3. A Valid Expression Can Still Fail at Evaluation Time

Successful parsing does not guarantee all references will resolve at runtime. Common runtime errors:

- Variable not registered in the EvaluationContext.
- Root object lacks the referenced property.
- Intermediate object is null when the expression accesses a subsequent property.
- Bean name not found by the BeanResolver.
- Method does not exist or has no matching signature.
- TypeConverter cannot convert an argument or result.
- Property does not support writing when the expression performs an assignment.
- Invoked method throws an exception or an external service fails.

Example:

    Expression expression =
            parser.parseExpression("#customer.address.city");

The expression can parse successfully even if the context has not registered the `customer` variable. The error only appears when calling `getValue(context)`. Similarly, the bean name in `@orderPolicy` may be syntactically valid yet fail to resolve if the context has no BeanResolver or matching bean.

Distinguish parse errors from evaluation errors to handle the root cause properly. Do not catch all exceptions and return a default value as if the expression had been validated.

## 4. Successful Evaluation Still Does Not Prove Safety

Even when an expression executes successfully and returns a result of the expected type, it can still exceed the privileges required by the use case.

A method can:

- Read data belonging to another tenant or user.
- Write or delete records.
- Send emails, publish messages, or call external APIs.
- Mutate object state or shared resources.
- Trigger bean initialization or access broadly privileged services.
- Perform resource-intensive computation over large collections.

For example, `@paymentService.refund(#paymentId)` can parse and can evaluate successfully if the bean and method are provided. That does not prove the caller is authorized to refund that payment. That permission must be verified at the business layer, based on principal, resource, tenant, state, and transaction rules.

**A valid result does not mean an authorized action.** Both context capabilities and business permissions must be verified at execution time.

## 5. EvaluationContext Determines Many Runtime Capabilities

EvaluationContext provides the components that govern what an expression can do:

| Component | Effect |
|---|---|
| Root object and variables | What data the expression can reference |
| PropertyAccessor | Which properties can be read or written |
| MethodResolver | Which methods can be located and invoked |
| BeanResolver | Which bean names can be resolved via `@beanName` |
| TypeLocator | Which classes can be referenced via `T(...)` |
| ConstructorResolver | Which constructors can be invoked via `new` |
| TypeConverter | Which type conversions are supported |

The same expression string can behave differently in two EvaluationContexts. A context with only a restricted root object may fail to resolve beans; a StandardEvaluationContext with a BeanFactoryResolver and reflective method access can open many more capabilities.

Therefore, safety cannot be judged from the expression string alone. You must inspect the actual context used during evaluation.

## 6. StandardEvaluationContext Is Not a Sandbox

StandardEvaluationContext provides flexible capabilities, typically including reflective property access, method invocation, and type/constructor resolution. When configured with a BeanResolver, expressions can also access beans by name.

This flexibility suits trusted internal expressions, but can be overly broad if the expression string comes from users or modifiable configuration.

Example:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setBeanResolver(
            new BeanFactoryResolver(beanFactory)
    );

The context above can resolve beans from BeanFactory. If the expression is supplied from an untrusted source, allowing a global resolver can expose many services beyond the current intent.

Do not treat parser acceptance of an expression or the use of StandardEvaluationContext as a security boundary. Restrict the objects, resolvers, accessors, and methods needed by the use case.

## 7. SimpleEvaluationContext Narrows Scope but Does Not Replace Policy

SimpleEvaluationContext is designed for restricted use cases like data binding. Depending on the chosen builder, it can restrict property access and write permissions; it does not support bean references, type references, or constructor invocation. Instance method invocation is not enabled by default.

Example of a read-only context:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(orderView)
                    .build();

This is the right choice when an expression only needs to read properties from a view model. If instance methods must be called, the builder can explicitly enable them with `withInstanceMethods()`; when doing so, review which methods are publicly exposed on the object.

SimpleEvaluationContext narrows the available feature set, but it does not automatically verify data access rights or business rules. If the root object contains data outside the user's scope, the expression can still read that data through allowed properties. Provide only authorization-checked objects appropriate to the use case.

## 8. Do Not Concatenate Untrusted Data into Expression Strings

A common design mistake is concatenating input directly into an expression:

    String source =
            "name == '" + userInput + "'";

    Expression expression = parser.parseExpression(source);

If `userInput` contains SpEL syntax characters, the resulting content may no longer be the condition the application intended to build. The user can alter the structure of the expression instead of merely supplying a data value.

Keep the expression fixed and pass data via variables:

    Expression expression =
            parser.parseExpression("name == #requestedName");

    context.setVariable("requestedName", userInput);

    Boolean matches =
            expression.getValue(context, Boolean.class);

Variable values still need type, length, and business-rule checks. However, they are passed as runtime data rather than concatenated into new SpEL code.

If users need to choose filter conditions or fields, prefer accepting a clearly schema-backed data structure, such as field names from an allowlist, operators from an enum, and separate values.

## 9. Defining a Permitted Expression Set

If the application must accept expressions configured by users or administrators, predefine an accepted set of syntax and capabilities. For example, a product filter might only allow:

- Reading a few allowlisted properties such as `price`, `category`, and `active`.
- Comparisons, logical combinations, and using literals or variables.
- No assignments.
- No bean references.
- No constructor invocation or type references.
- No method calls outside a predefined list.

As an additional control layer, you can parse the expression and inspect the AST structure against an allowlist. The checker must recursively process every node and reject unrecognized constructs; it must not allow new node types by default when upgrading Spring.

Do not use regexes or simple string searches like `contains("@")` to prove an expression is safe. Nested syntax, literals, and other expression forms can make string checks inaccurate. An AST allowlist also does not replace a restricted context and runtime authorization.

If general-purpose expression language support is unnecessary, a small DSL or schema-backed filter structure is usually easier to constrain and test.

## 10. Restrict Exposed Beans, Methods, and Properties

If an expression needs to call application logic, expose a narrow-API facade. Do not place the entire ApplicationContext, BeanFactory, repositories, or administrative services into the context.

Example:

    public final class OrderExpressionFacade {

        public boolean canPreview(OrderView order) {
            return order.isVisible();
        }

        public BigDecimal estimatedTotal(OrderView order) {
            return order.getTotal();
        }
    }

The facade provides only the operations required for the expression. If using bean references, use an allowlisted BeanResolver that resolves only permitted facades. If using variables, register only the exact objects needed for that evaluation.

Restrict simultaneously:

- Resolvable bean names.
- Callable methods on exposed objects.
- Readable or writable properties.
- Root object and variables placed into the context.
- Type references and constructor invocation if unneeded by the use case.

A bean allowlist is insufficient if that bean still exposes broadly privileged methods. Likewise, a narrow facade is insufficient if the root object contains sensitive data that the expression can read.

## 11. Check Permissions at Evaluation Time

Access rights can change depending on the caller, tenant, record state, or execution time. Therefore, do not check only once when saving an expression and assume the expression will always be allowed to run later.

Before evaluating or performing an important action, the application should:

1. Authenticate the current principal and tenant.
2. Load or select the root object within the scope permitted to the caller.
3. Check permissions on the specific resource.
4. Create the EvaluationContext with the right variables and capabilities.
5. Evaluate the expression within an appropriate transaction or service boundary.
6. Handle errors, record audit logs, and control side effects per policy.

If an expression is only used for filtering or display, prefer a read-only context and restricted objects. If an expression can mutate state, authorization must be checked in the service executing the action; do not rely on a parse result or a client-submitted condition.

## 12. Limiting Resources and Side Effects

An expression can be valid yet still consume significant resources or call methods repeatedly. Selection/projection over large collections, methods executing queries, or external service calls can increase processing time.

Measures to apply:

- Limit expression length and input data size.
- Limit sizes of collections placed into the context.
- Do not expose methods performing I/O or unbounded work to arbitrary expressions.
- Avoid repeatedly evaluating expressions with side-effecting methods.
- Use timeouts, transactions, and idempotency at the service layer when actions require them.
- Do not share an EvaluationContext holding request state across concurrent requests.

The parser is not an execution engine with a general-purpose resource sandbox. Limiting string length controls only part of the input; it does not guarantee an expression evaluates quickly or causes no side effects.

## 13. Distinguishing Parse Validation, Evaluation, and Authorization

These three steps answer three different questions:

| Step | Question | Evidence Obtained |
|---|---|---|
| Parse | Does the string match SpEL syntax accepted by the parser? | An Expression can be created |
| Evaluate | Can the expression run in a specific context? | A result or a runtime error |
| Authorization | Is the caller permitted to perform the operation on this data/resource? | Application permission decision |

Do not use the result of one step in place of another. Successful parsing does not prove evaluation will succeed. Successful evaluation also does not prove the action is permitted.

A secure system requires all three: constrained syntax, a least-privilege context, and authorization enforced at the proper business boundary.

## 14. Summary

`parseExpression(...)` parses syntax and creates an Expression; `getValue(...)` is what evaluates the expression in an EvaluationContext. Successful parsing does not verify that beans, methods, properties, or variables can resolve, and certainly does not prove runtime behavior is safe. An expression that evaluates successfully can still read out-of-scope data or perform side effects if the context grants those privileges. Do not concatenate untrusted input into SpEL strings; pass data via variables, restrict the root object and resolvers, prefer SimpleEvaluationContext for data binding, and use facades/allowlists when extra capabilities are required. Always check permissions at execution time and treat parse validation, evaluation, and authorization as three separate responsibilities.
