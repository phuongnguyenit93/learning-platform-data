# Document the Context, Beans, and Variables an Expression Requires

## Objectives

After this lesson, you will be able to fully document the dependencies a Spring Expression Language (SpEL) expression needs to parse and evaluate; describe the root object, variables, bean references, functions, property accessors, method resolvers, type conversion, and parser configuration; and turn that information into a testable contract. You will also know how to document data types, nullability, access permissions, lifecycle, side effects, potential errors, and how to initialize the corresponding EvaluationContext.

## 1. Why Document Expression Dependencies?

A SpEL string is usually short, yet it can depend on many components outside that string. For example:

~~~text
@pricingService.calculate(#order, #minimumTotal)
~~~

Looking at this expression alone is not enough to know:

- Where the pricingService bean is registered and what aliases it has.
- What type the bean has and what parameters the calculate method accepts.
- What type the order variable has, whether it can be null, and what data it contains.
- Whether minimumTotal is a BigDecimal, Integer, or another type.
- Which BeanResolver and TypeConverter the context has.
- Whether the method accesses external data or mutates state.
- Which root object and in which lifecycle the expression is evaluated.

If such details are not documented, maintainers have to guess from code or wait for runtime errors to discover missing dependencies. An expression can parse successfully yet still fail when the context lacks the required variables, beans, or accessors.

Dependency documentation turns an expression into a clear contract between the expression author, the Java code initializing the context, and the data passed in at runtime.

## 2. Distinguish ParserContext from EvaluationContext

The two contexts serve different roles:

| Component | Responsibility | Information to Document |
|---|---|---|
| ParserContext | Defines how the parser reads the string, such as template delimiters | Plain expression or template, prefix/suffix |
| EvaluationContext | Provides objects, variables, and access mechanisms during evaluation | Root type, variables, resolvers, accessors, converter |
| SpelParserConfiguration | Configures parser and compiler behavior | Compiler mode, auto-grow, limits, and ClassLoader |

Plain expression example:

~~~java
Expression expression =
    parser.parseExpression("#order.total >= #minimumTotal");
~~~

Template example:

~~~java
Expression expression = parser.parseExpression(
    "Order #{#order.id} is ready",
    new TemplateParserContext()
);
~~~

TemplateParserContext only tells the parser which parts are literal text and which parts are SpEL. It does not register variables, beans, or functions.

When writing documentation, include two separate sections: parse configuration and evaluation contract. Do not vaguely write that an expression needs "a context" without specifying whether it is ParserContext or EvaluationContext.

## 3. Specify the Root Object

The root object is the object used when evaluating properties without a # prefix. For example:

~~~text
customer.name
total >= #minimumTotal
#root.id
~~~

If the expression is evaluated with OrderView as the root object, properties such as customer and total must exist on OrderView or be accessed via an appropriate PropertyAccessor.

Documentation should record:

- The exact root object type, not just a conceptual name like Order.
- Which properties the expression reads.
- The type of each property.
- Whether each property can be null.
- Nested objects and their existence conditions.
- Where the root object is created and whether it is immutable during evaluation.
- Whether the root object contains services, entities, or sensitive data.

For example:

| Property | Type | Nullability | Purpose |
|---|---|---|---|
| id | String | Required | Order identifier |
| total | BigDecimal | Required | Computed total amount |
| customer | CustomerView | Nullable | Customer information |
| status | String | Required | Current status |

Prefer a small DTO or view as the root object. If an expression only needs id, total, and status, do not pass a full entity with relationships to repositories, credentials, or services.

## 4. Distinguish Unprefixed Properties from #variable

SpEL has distinct namespaces:

| Syntax | Data Source | Example |
|---|---|---|
| total | Property of the current evaluation object | total |
| #minimumTotal | Variable in the EvaluationContext | #minimumTotal |
| #root.id | Property of the initial root object | #root.id |
| #this.name | Property of the current evaluation object | #this.name |
| @pricingService | Bean resolved via BeanResolver | @pricingService |

If the root object has a name property and the context also has a name variable, the two references still differ:

~~~text
name
#name
#root.name
~~~

Documentation must state clearly which namespace each name belongs to. Do not write a generic list of names such as name, order, service without indicating how each is accessed.

With selection and projection, #this can shift to the current element, while #root continues to point to the original root object. If an expression uses collection operations, explicitly document which properties come from the element and which come from the root.

## 5. List Variables

Variables are registered into the EvaluationContext by the application and referenced using #.

For example:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("currentUserId", "U-1024");
context.setVariable("featureEnabled", true);
~~~

Expression:

~~~text
total >= #minimumTotal and #featureEnabled
~~~

For each variable, document:

| Field | Meaning |
|---|---|
| Name | Name after the # sign |
| Java type | Actual registered type |
| Required | Whether it must be present in the context |
| Nullable | Whether the value can be null |
| Meaning | Business meaning |
| Source | Java component providing the value |
| Constraints | Value range, format, or limits |
| Lifecycle | When the value is created/updated |

For example, the minimumTotal variable might be BigDecimal, required, non-null, and sourced from pricing policy configuration. The currentUserId variable might be a String obtained from the security context.

Do not merely document a variable as "number" or "user". Record the specific Java type and value contract so integrators do not pass the wrong type.

## 6. Distinguish Required, Optional, and Null Variables

There are three states to document separately:

- Required variable: must be registered before evaluation.
- Optional variable: may be absent or have a null value per contract.
- Variable with a default value: expression or Java code explicitly defines how to handle absence.

For example:

~~~text
#customer != null ? #customer.name : 'Guest'
~~~

This expression has a branch handling a null customer, yet documentation must still state whether customer can be null and why.

Do not treat an unregistered variable as identical to a variable registered with null. Depending on usage, the two cases can lead to different results or errors.

If a variable is required, verify its presence and type in Java before calling getValue. If a variable is optional, document where safe navigation, Elvis, or null conditions are applied.

## 7. Document Bean References and Aliases

Bean references use the @ syntax:

~~~text
@pricingService.calculate(#order)
~~~

When a context is created manually, bean references require a BeanResolver. With a Spring BeanFactory, BeanFactoryResolver can be used:

~~~java
context.setBeanResolver(
    new BeanFactoryResolver(beanFactory)
);
~~~

Documentation for each bean should record:

| Field | Example Content |
|---|---|
| Bean name | pricingService |
| Alias | pricing.service if any |
| Java type | PricingService |
| Method called by expression | calculate(OrderView) |
| Registration source | Spring configuration |
| Scope/lifecycle | singleton, request, or other scope |
| Side effect | Pure calculation or accesses external systems |
| Access permission | Who is permitted to use this expression |

If a bean name contains dots or special characters, SpEL may require enclosing the name in a string literal, for example:

~~~text
@'pricing.service'.calculate(#order)
~~~

Record the exact name or alias registered in the container. Do not assume the parser automatically normalizes dots, hyphens, or letter casing.

## 8. Do Not Provide Beans Broader Than Needed

Every bean exposed to an expression can open up additional methods and dependencies for the expression to invoke.

If the expression only needs a pricing calculation result, you can call the service in Java beforehand and pass the result:

~~~java
context.setVariable(
    "calculatedTotal",
    pricingService.calculate(order)
);
~~~

The expression only needs:

~~~text
#calculatedTotal >= #minimumTotal
~~~

In the documentation, explain why a bean reference is used and why passing a precomputed value instead is not feasible. If a bean is genuinely required, document which methods are invoked, arguments, side effects, and required permissions.

Do not simply state that the expression has access to ApplicationContext. Specify the exact BeanResolver and the scope of beans it is able to resolve.

## 9. Document Registered Functions

A function is a Java Method registered in EvaluationContext and invoked with the syntax #functionName(...).

For example:

~~~java
Method normalizeMethod =
    TextFunctions.class.getMethod("normalize", String.class);

context.registerFunction("normalize", normalizeMethod);
~~~

Expression:

~~~text
#normalize(#customerCode)
~~~

For each function, document:

- Function name in SpEL.
- Class declaring the Method.
- Full method signature.
- Parameter types and order.
- Return type.
- Null handling rules.
- Whether it throws any exceptions.
- Whether it has side effects.
- Whether it is called repeatedly in selection/projection.

Functions typically use static methods. If you need to invoke a method on a service instance with dependencies, consider a bean reference or calling the service in Java.

Functions and variables share the same namespace. Do not register a variable with the same name as a function because setVariable can overwrite the registered Method in a way that prevents the expression from invoking the function as intended.

## 10. Document PropertyAccessor and Read/Write Permissions

PropertyAccessor determines how SpEL reads or writes properties on a target object.

Documentation should record:

- Default accessor or custom accessors registered.
- Target types supported by the accessor.
- Properties allowed for reading.
- Properties allowed for writing.
- How missing properties are handled.
- How null targets are handled.
- Whether the accessor falls back to another accessor.

For example:

| Target type | Property | Read | Write |
|---|---|---|---|
| OrderView | id | Yes | No |
| OrderView | total | Yes | No |
| OrderView | status | Yes | No |
| OrderEntity | internalNote | Restricted | No |

If an expression only reads data, explicitly note that the context is read-only. If assignment or setValue is used, specify exact write permissions and the accessor enforcing control.

Do not treat a public setter as proof that an expression is permitted to write. Write capability depends on the active context and accessors.

## 11. Document Method Resolvers and Invoked Methods

MethodResolver determines whether SpEL can locate and invoke methods on objects.

For StandardEvaluationContext, specify whether default resolvers or custom resolvers are used. For SimpleEvaluationContext, instance method invocation is not enabled by default; if the builder enables this capability, document why it is required.

Each method called by an expression should record:

- Target type.
- Method name and signature.
- Argument types.
- Return type.
- Access permissions.
- Side effects and expected execution time.
- Exceptions that may be thrown.

A data-reading expression can accidentally call a state-mutating method if the passed-in object has that method and the context permits it. A root DTO with getters only helps narrow the surface of accessible methods.

## 12. Document TypeConverter and Conversion Rules

SpEL uses the EvaluationContext's TypeConverter when converting results, assigning properties, or passing method arguments to target types.

Documentation must record:

- Specific TypeConverter.
- StandardTypeConverter or custom converter.
- Connected ConversionService if any.
- Type pairs that are converted.
- Relevant format, locale, or timezone.
- How null values and empty strings are handled.
- Conversion errors that may occur.

For example, an expression passes the string '42' to a method expecting Long. If the converter supports it, SpEL can convert the argument before calling the method.

Conversion is not validation. Successfully converting a string into an Integer does not prove the number falls within business limits. Documentation must separately describe validation rules and where they are enforced.

## 13. Document TypeLocator and ConstructorResolver When Present

If an expression uses type references or constructors:

~~~text
T(java.time.LocalDate)
new java.math.BigDecimal('125.50')
~~~

document the TypeLocator and ConstructorResolver in use, which types are allowed to be referenced, and which constructors may be called.

Information to record:

- Fully qualified class name.
- Constructor signature.
- Argument types and limits.
- Whether objects are instantiated on every evaluation.
- Whether the constructor performs I/O or has side effects.
- Who is responsible for lifecycle management and closing resources.
- Whether there is an allowlist or package/type restriction.

If an expression does not need to instantiate objects, state clearly that constructor invocation is not provided or not in scope. Do not grant a broad context merely for convenience on a property-reading expression.

## 14. Document Parser Configuration

An expression can depend on SpelParserConfiguration:

- Compiler mode: OFF, IMMEDIATE, or MIXED.
- ClassLoader used for compiled expressions.
- Auto-grow null references.
- Auto-grow collections.
- Maximum auto-grow size.
- ParserContext and template delimiters.

If the expression is parsed as a template, record the exact prefix/suffix. If the compiler is enabled, record the mode and the requirement that runtime data types remain stable.

Parser configuration does not replace EvaluationContext. Document both parts separately so operators know how the string is parsed and with which privileges/data the expression is evaluated.

## 15. Document Collection Shapes and Nested Data

If an expression uses selection or projection, documentation must describe the collection structure:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

Example contract:

| Data | Type | Condition |
|---|---|---|
| orders | List<OrderView> | May be empty, non-null |
| element | OrderView | Non-null |
| total | BigDecimal | Non-null |
| id | String | Required |
| minimumTotal | BigDecimal | Required |

Specify whether the collection can be null or empty, whether it is ordered, whether elements can be null, and what the result is when no element matches.

Selection typically returns an empty collection when no elements match. First/last selection can return null when no matching element is found. Projection produces results for the source elements and does not filter them automatically.

If the expression uses #this, document which element #this represents at each nesting level. If root data is needed inside a collection operation, document the #root reference explicitly.

## 16. Document Result Type and Output Contract

Every expression should have an expected result type:

- String for messages or labels.
- Boolean for conditions.
- BigDecimal for monetary calculations.
- Collection for selection/projection.
- Object or DTO if the expression constructs a data structure.

Also record:

- Whether null can be returned.
- Whether getValue(context, targetType) is required.
- Whether output conversion applies.
- What element type a collection has.
- Whether the value is used to write data or drive business decisions.

Example expression:

~~~text
total >= #minimumTotal
~~~

has a Boolean output contract. If the application requires a non-null Boolean, specify how null total or null minimumTotal is handled instead of leaving callers to guess.

For BigDecimal, specify scale, currency, and rounding rules at the business layer if the result represents money.

## 17. Complete Dependency Documentation Example

An expression record can be structured as follows:

~~~text
Expression ID: order-eligibility-v1
Purpose: Check whether the order meets the minimum threshold
Source: total >= #minimumTotal and active

Parser:
  Type: Standard SpelExpressionParser
  ParserContext: Plain expression
  CompilerMode: OFF

Root object:
  Type: OrderView
  Properties:
    total: BigDecimal, required
    active: boolean
  Mutable: No

Variables:
  minimumTotal:
    Type: BigDecimal
    Required: Yes
    Nullable: No
    Source: PricingPolicy

Beans:
  None

Functions:
  None

Access:
  PropertyAccessor: Read-only data binding
  Method invocation: Not required
  BeanResolver: Not configured
  Type reference: Not required
  Constructor invocation: Not required

Conversion:
  StandardTypeConverter
  No custom conversion required

Result:
  Type: Boolean
  Nullable: No

Errors:
  Missing root property
  Missing minimumTotal variable
  Incompatible total type
~~~

This is an illustrative example showing how to document a contract. Actual values must be taken from the expression and how the application constructs its context; do not copy example names or types if the project uses a different structure.

## 18. Java Example Initializing Context per Contract

Suppose the expression only requires OrderView and minimumTotal:

~~~java
public record OrderView(
        BigDecimal total,
        boolean active) {
}

public Expression createEligibilityExpression() {
    return new SpelExpressionParser().parseExpression(
        "active and total >= #minimumTotal"
    );
}

public Boolean evaluate(
        Expression expression,
        OrderView order,
        BigDecimal minimumTotal) {

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("minimumTotal", minimumTotal);

    return expression.getValue(
        context,
        order,
        Boolean.class
    );
}
~~~

Contract of the code snippet:

- Root type is OrderView.
- total is BigDecimal and active is boolean.
- minimumTotal is a required variable of type BigDecimal.
- No bean references or functions are needed.
- No property writes or method calls are needed.
- Result is Boolean.

If the expression changes to use a bean, function, or method, both the context-building code and the dependency documentation must be updated. Never let a new expression depend on a capability the context does not yet supply.

## 19. Lifecycle and Context Sharing Scope

Documentation must clearly specify how Expression and EvaluationContext instances are created, stored, and reused.

Typically a fixed expression can be parsed once and reused. EvaluationContext, on the other hand, can hold a root object and variables that change per request.

If a mutable context is shared across multiple requests, one request can overwrite a variable or root object being used by another request. This can cause data leaks or nondeterministic results.

Document:

- Whether the Expression is parsed at startup, on configuration reload, or per request.
- Whether the parser is shared.
- Whether the context is created per request, transaction, or job.
- Where variables are updated.
- Whether the context holds mutable state.
- Whether any resolver or accessor holds state.
- Who is responsible for creating and releasing resources.

Prefer reusing Expression alongside a separate EvaluationContext for each unit of work needing isolated data. Do not share a mutable context without an explicit synchronization and isolation design.

## 20. Document Expected Configuration and Runtime Errors

Each expression should list potential errors and their classification:

| Error | Category | Where Checked |
|---|---|---|
| Syntax error | Parse/configuration | When loading expression |
| Missing variable | Context setup or runtime | Before evaluation |
| Wrong bean name | Dependency/configuration | When creating context or evaluating |
| Non-existent property | Model/accessor contract | Test against root type |
| Null property | Runtime data | During evaluation |
| Conversion failure | Data or converter config | During type conversion |
| Out-of-bounds value | Business validation | After conversion |
| Method throws exception | Method/runtime logic | During evaluation |

Document important exception types or causes, the expression identifier, and the responsible handler. Do not log full objects, passwords, tokens, or sensitive data.

If an expression is static configuration, parse and verify dependencies as early as possible. If an expression depends on request data, validate static parts first and handle specific data at the business boundary.

## 21. Document Access Permissions and Security Risks

The context is part of the security boundary. Documentation should record:

- Whether the root object contains sensitive data.
- Which properties are allowed for reading or writing.
- Which methods can be invoked.
- Which beans are resolved.
- Which functions are registered.
- Whether type references or constructor invocations are permitted.
- Whether the expression comes from code, config files, administrators, or users.
- Who has permission to modify the expression.
- Whether output is placed into HTML, email, SQL, or URLs.

For untrusted expressions, prefer a small root object, a read-only context, and no beans or side-effecting methods. Do not treat ParserContext or successful parsing as a sandbox.

If output is inserted into HTML/email, encode it appropriately for the output context. SpEL does not automatically escape content.

## 22. Testing the Dependency Contract

Dependency documentation should be paired with tests so it does not become stale.

Positive tests verify:

- The expected root object type is accessed.
- All required variables are registered.
- Required beans/functions are resolved.
- Properties and methods are accessed correctly.
- Result type and output value are correct.

Negative tests verify:

- Missing required variables are detected.
- Beans outside the allowlist are not resolved.
- Disallowed property reads/writes are rejected.
- Unnecessary methods cannot be invoked.
- Out-of-scope constructors or type references are rejected.
- Null or mistyped data is handled according to the contract.

Example testing expression parsing and evaluation:

~~~java
@Test
void eligibilityExpressionUsesDocumentedInputs() {
    Expression expression =
        new SpelExpressionParser().parseExpression(
            "active and total >= #minimumTotal"
        );

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable(
        "minimumTotal",
        new BigDecimal("100.00")
    );

    OrderView order = new OrderView(
        new BigDecimal("125.00"),
        true
    );

    assertEquals(
        Boolean.TRUE,
        expression.getValue(context, order, Boolean.class)
    );
}
~~~

Beyond result tests, test contexts with missing variables and boundary data. A test that parses successfully does not prove all dependencies were properly registered.

## 23. Managing Changes and Expression Versions

When an expression changes, its dependency contract can change as well. For example, adding `@pricingService.calculate(...)` introduces a bean dependency; adding `#discountRate` adds a variable; adding `new SomeType(...)` adds a constructor dependency.

Attach an identifier and version to expressions stored outside code. On every change, update:

- Expression source.
- Root object type and property paths.
- Variable names, types, and nullability.
- Bean names, aliases, and method signatures.
- Function signatures.
- Accessor/resolver/converter configuration.
- Result type.
- Security review and related tests.

Do not edit only the expression string and forget to update context-building code. Conversely, do not add a bean or function to the context without documenting the reason and dependent usage.

Versions can be used to pinpoint exactly which expression was deployed when investigating runtime errors.

## 24. Dependency Table Template for Each Expression

A concise template can be used consistently:

| Item | Content to Fill In |
|---|---|
| Expression ID/version | Stable name and revision |
| Purpose | Business purpose |
| Source | SpEL string or template |
| ParserContext | Plain expression or template; delimiters |
| Parser configuration | Compiler mode, auto-grow, ClassLoader |
| Root object | Type, property paths, nullability |
| Variables | Name, Java type, required, nullable, source |
| Beans | Name/alias, type, methods, scope, side effects |
| Functions | Name, Method signature, arguments, return type |
| Property access | Accessor, read/write allowlist |
| Method access | Resolver and permitted methods |
| Type conversion | TypeConverter, ConversionService, custom rules |
| Type/constructor | TypeLocator, ConstructorResolver, allowed types |
| Result | Type, nullability, collection shape |
| Errors | Parse, context, conversion, runtime, validation |
| Security | Expression source, edit permissions, sensitive data |
| Lifecycle | Parse, context creation, reuse, cleanup |
| Tests | Positive, negative, null, boundary, missing dependency |

Not every expression needs to use every capability. For non-applicable items, explicitly write "Not used" rather than leaving blanks that leave readers unsure whether the item was reviewed.

## 25. Key Takeaways

An expression only works properly when the source string, ParserContext, EvaluationContext, and runtime data align. Document root objects, variables, bean references, functions, property accessors, method resolvers, TypeConverter, TypeLocator, ConstructorResolver, and parser configuration separately.

For each dependency, record the exact name, Java type, nullability, provider source, lifecycle, access permissions, and potential errors. Distinguish unprefixed properties from #variables, #root from #this, and @beans from #name functions.

Prefer small root DTOs, strongly typed variables, and contexts supplying only necessary capabilities. If an expression does not need beans, methods, constructors, or property writes, explicitly document that those capabilities are not used. Documentation should be accompanied by positive/negative tests so expression changes do not accidentally expand privileges or leave missing dependencies.

## References

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [PropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html)