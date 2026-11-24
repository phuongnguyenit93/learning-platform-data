# Standardize How Expressions Are Written Across Modules

## Objectives

When multiple modules use Spring Expression Language (SpEL), each module can develop its own habits for naming variables, writing conditions, handling nulls, configuring parsers, and testing expressions. Without shared conventions, the same rule can be written in many different styles, making reviews, maintenance, Spring upgrades, and error diagnostics difficult.

Standardizing does not mean every module must use identical expressions. The goal is to unify what can be shared: syntax, naming, data scoping, type semantics, EvaluationContext configuration, error handling, security, and testing workflows. Each module can still have its own rules, yet readers know how to locate the root object, variables, functions, and null behavior in any expression.

After this lesson, you will be able to:

- Establish shared SpEL conventions across multiple modules.
- Name expressions, variables, and functions consistently.
- Write expressions with clear root object and current element scopes.
- Unify null handling, numeric semantics, and conversion.
- Standardize selection, projection, templates, and type references.
- Share parser/context factories while keeping per-request data isolated.
- Manage functions, bean references, and access privileges under control.
- Version rules, cache Expressions, and test to a common standard.
- Embed conventions into reviews, documentation, and release workflows.

## 1. General Design Principles

A good convention helps readers quickly answer these questions:

1. Which business rule does this expression serve?
2. What type is the root object and what data does it hold?
3. Which variables are supplied by the EvaluationContext?
4. What type does the expression return?
5. How are nulls and invalid data handled?
6. Which functions or methods are permitted?
7. How are the parser and EvaluationContext configured?
8. Where are rules versioned, tested, and modified?

Apply the following principles:

- **Clarity before brevity:** prefer understandable variable names and expressions over short but ambiguous writing.
- **Explicit typing:** specify the types of root, variables, arguments, and results.
- **No side effects:** expressions primarily read data and compute values.
- **Centralized configuration:** parsers and EvaluationContexts are created through a shared mechanism.
- **Per-request data isolation:** never share mutable contexts across independent requests.
- **Tested:** every rule has tests for true, false, and boundary values.
- **Versioned:** sources and related configurations are managed for traceability.
- **Least privilege:** provide only the objects, properties, methods, and functions a rule needs.

## 2. Expression Naming and Identifier Conventions

Each expression should have a stable identifier describing its module and business purpose. Do not use the full source text as the display name for operators.

An identifier pattern could be:

~~~text
<module>.<domain>.<rule-purpose>
~~~

For example:

~~~text
checkout.order.minimum-total
billing.invoice.tax-eligibility
catalog.product.visible-to-customer
shipping.address.serviceable
~~~

Naming conventions should be consistent:

- Use lowercase letters and dots for hierarchy.
- Use business-meaningful words; avoid generic technical names like rule1 or expressionA.
- Keep the ID stable across source edits.
- Increment the version when semantics or source change.
- Record the owner or module responsible for the rule.
- Do not embed request, user, or tenant details in the ID.
- Separate the rule ID from the expression content and from internal cache keys.

If the system serves multiple tenants with custom rules, namespaces or tenant ownership must be managed at the registry and authorization layer. Do not rely on a client-supplied ID name to determine permissions.

## 3. Expression Formatting Conventions

Expressions should be written so conditions can be read and reviewed independently. For long conditions, break lines by logical group instead of packing everything into one hard-to-read string.

For example:

~~~text
#root.active
and #root.total.compareTo(#minimumTotal) >= 0
and #root.status == #requiredStatus
~~~

Formatting conventions:

- Place each main business condition on its own line when an expression is long.
- Use spaces around operators for readability.
- Use parentheses whenever precedence is not obvious.
- Group related conditions with line breaks and explain them in accompanying documentation.
- Avoid nesting too many ternaries or logical operators in a single expression.
- Avoid repeating the same long condition in multiple places.
- Do not insert comments inside an expression if the syntax or storage medium does not support comments.
- Do not use unexplained abbreviations in variable names.
- Use one consistent quote style for string literals in SpEL.

Example with grouped conditions:

~~~text
(
    #root.active
    and #root.status == #requiredStatus
)
and #root.total.compareTo(#minimumTotal) >= 0
~~~

If an expression grows so long that it takes multiple reads to understand, move part of the logic into a descriptively named pure function or split the rule into named steps in Java. Do not try to keep all logic in one string simply because SpEL can express it.

## 4. Root Object and #this Scope Conventions

Each module should define a clearly structured root model for its rule group. Rule documentation should record the root type, readable properties, and expected result type.

Use **#root** when you want to reference root data explicitly:

~~~text
#root.order.total >= #minimumTotal
~~~

Use **#this** when you need to specify the current object inside a collection operation:

~~~text
#root.orders.?[
    #this.active and #this.total >= #minimumTotal
]
~~~

In collection selection or projection, #this is the current element of that operation. When collection operations are nested, #this shifts with the level being processed. Therefore:

- Use #root for root data that must remain referenced throughout the expression.
- Use #this for the element currently processed by selection or projection.
- Do not rely on bare properties when an expression has multiple levels and scope could become ambiguous.
- Document element types at every level when expressions are nested.
- Avoid changing the meaning of the root object across versions of the same rule ID.

Nested collection example:

~~~text
#root.departments.![ 
    #this.employees.?[
        #this.active and #this.salary >= #minimumSalary
    ].![#this.name]
]
~~~

The result is a list of employee names per department; nested projection preserves the sublist structure. Do not assume the result is automatically flattened.

## 5. Variable Naming and Type Conventions

Variables from EvaluationContext must have consistent names between registration and usage. When calling setVariable(), pass the name without #; in the expression, reference it with #name.

For example:

~~~java
context.setVariable("minimumTotal", minimumTotal);
context.setVariable("requiredStatus", OrderStatus.APPROVED);
context.setVariable("allowedRegions", allowedRegions);
~~~

Expression:

~~~text
#root.total >= #minimumTotal
and #root.status == #requiredStatus
and #allowedRegions.contains(#root.region)
~~~

Naming conventions:

- Use lowerCamelCase.
- Names should convey business meaning, not just data types.
- Include units or bounds where confusion could arise: minimumTotal, maximumAge, timeoutSeconds.
- Use enums instead of status strings when the model provides a suitable enum.
- Use BigDecimal for money or decimal numbers requiring precision.
- Use collections with explicit generic types.
- Avoid overly generic names like value, data, x, or limit when multiple values of the same kind exist.
- Manage variable names centrally via constants or a well-defined parameter object schema.

Every rule should declare its list of input variables, types, required/optional status, and null semantics. Do not force operators to deduce required variables solely by reading the expression source.

## 6. Null Handling Conventions

Modules need to agree on what null means before writing expressions. Null can represent invalid data, an unset state, or an optional value. Do not let each expression implicitly pick a different handling style.

Rules to document clearly:

- Is the root object allowed to be null?
- Are intermediate properties allowed to be null?
- Is a null collection treated as empty or an error?
- Are null elements inside a collection allowed?
- Does a null optional variable mean skipping the condition or not?
- Can getters or functions return null?

Example checking a possibly null customer:

~~~text
#root.customer?.active == true
~~~

If null must be rejected, the expression can state it explicitly:

~~~text
#root.customer != null and #root.customer.active
~~~

For nullable collections, define a policy before using selection. Null-safe collection operations depend on the Spring version; confirm the framework version supported by the module before using that syntax.

Do not use safe navigation to mask missing properties or a broken model. Safe navigation only handles a null target at the point where it is applied.

## 7. Numeric and Conversion Conventions

Modules must agree on how numbers are handled, especially when expressions involve money, rates, limits, and time.

Recommendations:

- Use BigDecimal for currency and decimal math requiring precision.
- Do not mix String, Integer, Double, and BigDecimal in the same rule without explicit conversion rules.
- Compare BigDecimal numerically using compareTo when scale is not part of the contract.
- Define rounding mode and scale at the business layer.
- Specify an explicit target type when calling getValue(context, TargetType.class).
- Use the application's shared ConversionService when rules require conversion.
- Register custom Converters through centralized configuration.
- Validate data before evaluation if format carries business constraints.

Example comparing monetary amounts:

~~~text
#root.total.compareTo(#minimumTotal) >= 0
~~~

Do not rely on implicit conversion to turn an arbitrary string into a monetary amount. If input data is a String, parse and validate it at the application boundary, then pass the normalized BigDecimal into the context.

## 8. Collection Operations Conventions

Modules should consistently use selection and projection syntax:

- **.?[predicate]** filters elements.
- **.![projection]** transforms each element into a result.
- **.^[predicate]** selects the first matching element.
- **.$[predicate]** selects the last matching element.

Selection example:

~~~text
#root.orders.?[#this.active]
~~~

Projection example:

~~~text
#root.orders.![#this.id]
~~~

First-match selection example:

~~~text
#root.orders.^[#this.status == #requiredStatus]
~~~

Usage conventions:

- Predicates return an explicit Boolean.
- Do not call side-effecting functions inside selection/projection.
- Define collection element types.
- Define behavior for empty and null collections.
- Do not assume nested projections flatten automatically.
- Do not depend on Set or Map iteration order unless the implementation guarantees it.
- For complex filtering, grouping, sorting, or flattening, consider performing them in Java.

If a collection holds multiple element types, normalize the model or use explicit type-checking conditions. Do not let a shared expression rely on properties present only on certain elements without protective guards.

## 9. Function and Method Call Conventions

Functions registered in EvaluationContext should typically be small public static methods with stable signatures and behavior-describing names.

For example:

~~~java
context.registerFunction(
    "normalizeCode",
    TextFunctions.class.getMethod("normalizeCode", String.class)
);
~~~

Call in an expression:

~~~text
#normalizeCode(#root.code)
~~~

Conventions:

- Function names use lowerCamelCase and describe behavior.
- Arguments and return types must be clear.
- Functions should be pure: same input yields same output, no external state changes.
- Null behavior must be defined.
- Do not use static functions to hold dependencies or replace Spring services.
- Do not call side-effecting methods in expressions.
- Register only the functions the module actually needs.
- Use a context factory to register functions consistently.

If you need repositories, API clients, transactions, or multi-step logic, move to a Spring-managed Java service. SpEL should combine data and conditions; it should not become the orchestrator for the entire business flow.

## 10. Bean Reference and Type Reference Conventions

Bean references via @beanName can couple expressions to the container and bean resolver:

~~~text
@taxPolicy.currentRate
~~~

Use only when a module has a clear need and the context supports BeanResolver. If the goal is merely injecting a bean into a property, prefer standard dependency injection.

Type references use T(...) to access static members or enums:

~~~text
T(java.math.RoundingMode).HALF_UP
~~~

Conventions:

- Use fully qualified class names for classes outside java.lang.
- Do not register separate import prefixes in different modules without a shared convention.
- Limit bean references in business rules when necessary data can be passed via variables.
- Do not use static methods with side effects.
- Document rule dependencies on external beans or classes.
- Enable type/bean resolution only when the EvaluationContext and expression source are controlled.

## 11. Template Expression Conventions

If an expression mixes static text with dynamic content, explicitly define the template mode and delimiters.

Default:

~~~text
Hello, #{#customerName}!
~~~

You can use TemplateParserContext or ParserContext.TEMPLATE_EXPRESSION. If content frequently contains the #{ prefix as literal text, choose custom delimiters and record the delimiters in the rule metadata.

Distinguish:

- Template delimiter #{...} marks an expression block.
- String literals inside SpEL use quotes per SpEL syntax.
- XML/JSON/Java strings have their own escaping rules.
- Property placeholders and SpEL are two separate mechanisms.

Do not assume backslash is the escape mechanism for template delimiters if the ParserContext does not define that rule. User-supplied templates still execute SpEL inside expression blocks; custom delimiters are not a security control.

## 12. Parser Configuration and EvaluationContext Factory

Modules should use a shared parser factory or registry to configure:

- Compiler mode.
- Compiler class loader.
- ParserContext for templates.
- Auto-grow behavior if needed.
- Configuration limits appropriate for the Spring version.

Similarly, use an EvaluationContext factory to configure consistently:

- PropertyAccessor.
- MethodResolver.
- ConstructorResolver if genuinely required.
- TypeLocator.
- TypeConverter/ConversionService.
- BeanResolver if permitted.
- Function registrations.

Example context creation structure:

~~~java
public StandardEvaluationContext createContext(
        Object rootObject,
        RuleParameters parameters) {

    StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

    context.setVariable("minimumTotal", parameters.minimumTotal());
    context.setVariable("requiredStatus", parameters.requiredStatus());
    context.setTypeConverter(
        new StandardTypeConverter(applicationConversionService)
    );

    registerApprovedFunctions(context);
    return context;
}
~~~

This is an illustrative structure; method names, parameter objects, and APIs should be adapted to the project's Java/Spring version.

Shared configuration should be stable, while the root object and request-scoped variables must be created per evaluation. Do not cache mutable contexts containing request data in singletons or shared caches.

## 13. Compiler and Performance Conventions

The SpEL compiler can speed up certain expressions, but it relies on observed runtime types and does not support every expression construct.

General conventions should be:

- Keep compiler OFF by default unless backed by benchmarks and explicit requirements.
- Enable compilation only for supported expressions with stable runtime types.
- Use IMMEDIATE when compiled evaluation errors should be returned to the caller.
- Use MIXED when falling back to the interpreter is acceptable.
- Do not place side effects in expressions that MIXED may re-evaluate.
- Configure the compiler class loader so it can see the relevant types.
- Measure parse time and evaluate time separately.
- Do not assume every expression is compiled just because compiler mode is enabled.

If a module needs a different compiler mode, document the reason, rule scope, and corresponding tests. Avoid letting modules choose compiler modes independently without documentation because error behavior and performance can differ.

## 14. Rule Caching and Versioning

Parsed Expressions can be cached when sources are used repeatedly. Cache keys should distinguish at least:

- Rule ID.
- Rule version or source hash.
- ParserContext/delimiters.
- Parser configuration identity.
- Compiler mode and class loader if they affect the expression.

Use a bounded cache if the number of rules can grow. Have an invalidation policy when source, version, or configuration changes.

Do not cache an EvaluationContext containing a root object and request variables. Do not cache evaluation results without accounting for all dependencies such as inputs, user, tenant, time, bean state, and configuration.

When a rule changes:

1. Create a new version or invalidate the old entry.
2. Parse the new source with the current parser configuration.
3. Validate the expression and metadata.
4. Run the rule test suite.
5. Release the new version following the workflow.
6. Record the version used during evaluation for traceability.

## 15. Security and Privilege Restrictions

Expressions can read properties, call methods, reference types, beans, functions, or constructors depending on the EvaluationContext. Therefore, provisioning the context is a security decision.

Modules must agree on:

- Which sources are permitted to create or modify expressions.
- Who has permission to activate rule versions.
- Which objects and variables may be placed into the context.
- Which PropertyAccessors and MethodResolvers are registered.
- Whether type references, constructors, or bean references are permitted.
- Which functions are exposed.
- Whether expressions are permitted to invoke methods with side effects.
- Limits on source length, rule count, and processing time if applicable.

Prefer a least-privilege context. Use SimpleEvaluationContext when a restricted set of operations meets needs; use StandardEvaluationContext when broader capabilities are required and controlled.

Do not treat changing delimiters, using fully qualified names, or caching expressions as security measures. If expressions are untrusted, restrict both parser/context capabilities and data sources.

## 16. Common Testing Standards

Every module should maintain the same baseline test suite:

- Parses successfully with the real parser configuration.
- Correct result for valid inputs.
- False result when conditions are not met.
- Values equal to and adjacent to thresholds.
- Nulls in root, intermediate properties, variables, and collection elements.
- Successful and failed conversions.
- Empty, single-element, multi-element collections, and ordering.
- Missing, mistyped, or exception-throwing functions/methods.
- Fresh context does not retain state from a previous request.
- New expression version does not use stale cache entries.
- Access privileges do not exceed configuration.
- SpEL results cross-checked against independent Java reference logic.

For critical rules, write an independent Java reference or expected values to detect expressions that misrepresent business logic. Do not write a Java reference that merely calls the SpEL expression again.

Parameterized tests can run multiple datasets against the same expression. For wide input domains, use differential testing and save inputs/seeds when discrepancies are found.

## 17. Error Handling and Logging Conventions

Each module should handle errors with the same structure:

1. Distinguish parse errors from evaluation errors.
2. Record rule ID and version.
3. Record the message code and expression position if available.
4. Identify the operation kind: property, method, constructor, or conversion.
5. Preserve the cause chain for diagnostics.
6. Translate technical errors into business errors at the appropriate boundary.
7. Do not swallow exceptions and return null/false unless that is the contract.

Logs should include correlation ID, rule ID/version, root type, and necessary error details. Do not log passwords, tokens, object graphs, or full variables that may contain sensitive data.

Do not depend on exact exception message text to drive control flow. Message wording can change across Spring versions; message codes and exception types are usually more reliable for classification.

## 18. Sample Metadata for an Expression

Beyond the source, store minimal metadata so other modules can understand and operate the rule.

Example structure:

~~~yaml
id: checkout.order.minimum-total
version: 3
module: checkout
description: Order must be active and meet the configured minimum total.
rootType: com.example.checkout.Order
resultType: java.lang.Boolean
variables:
  minimumTotal:
    type: java.math.BigDecimal
    required: true
  requiredStatus:
    type: com.example.checkout.OrderStatus
    required: true
nullPolicy: required-values-must-not-be-null
parser:
  mode: standard-expression
  compiler: off
functions: []
owner: checkout-team
~~~

This is illustrative metadata, not a Spring-mandated format. Projects can use a database, YAML, JSON, or another registry, but should store enough information to validate and trace rules.

Do not store secrets or request values in metadata. Metadata describes contracts and configuration; actual data is passed through EvaluationContext during evaluation.

## 19. Workflow for Introducing a New Expression into a Module

1. **Describe the rule:** record purpose, owner, root type, and result type.
2. **Declare inputs:** list variables, types, required/optional, and null policy.
3. **Write the expression:** follow naming, formatting, and #root/#this scope conventions.
4. **Identify capabilities:** required property, method, function, type, or bean references.
5. **Use shared factories:** build the parser and EvaluationContext using module configuration.
6. **Check security:** supply only necessary data and permissions.
7. **Write tests:** happy path, negative path, null, conversion, collection, and Java reference.
8. **Version:** store source alongside metadata and version.
9. **Release:** invalidate appropriate caches and record the new version.
10. **Monitor:** observe errors, evaluation latency, and rule changes.

## 20. Cross-Module Review Checklist

Before merging or releasing an expression, verify:

- [ ] Rule has a clear ID, owner, and version.
- [ ] Root type and result type are documented.
- [ ] Variables have names, types, and required/null policies.
- [ ] #root and #this are used within proper scope.
- [ ] Expression is formatted per shared conventions.
- [ ] Null handling is consistent with the contract.
- [ ] Numeric types, precision, and rounding are clear.
- [ ] ConversionService and custom converters are centrally configured.
- [ ] Selection/projection results and ordering are defined.
- [ ] Functions are pure without unintended side effects.
- [ ] Bean/type/constructor access is enabled only when required.
- [ ] Parser and EvaluationContext factories are used properly.
- [ ] Request contexts are not shared or cached.
- [ ] Compiler mode is justified and appropriately tested.
- [ ] Cache key reflects source/version/parser configuration.
- [ ] Invalidation occurs when rules or configurations change.
- [ ] Independent Java reference or expected values exist.
- [ ] Appropriate null, conversion, collection, exception, and concurrency tests exist.
- [ ] Logging does not leak sensitive data.
- [ ] Metadata and operational docs are updated.

## Conclusion

Standardizing SpEL across modules requires unified conventions for rule identifiers, expression formatting, variable naming, #root/#this scoping, nulls, conversions, collections, functions, and access control. Parser configuration and EvaluationContext factories should be centrally managed, while each request's root data and variables must stay isolated. Cache parsed Expressions by source/version and parser configuration; test against independent Java references; version and invalidate when rules change. When modules adhere to a clear contract, expressions become easier to review, operate, and upgrade while preserving flexibility for each business domain.