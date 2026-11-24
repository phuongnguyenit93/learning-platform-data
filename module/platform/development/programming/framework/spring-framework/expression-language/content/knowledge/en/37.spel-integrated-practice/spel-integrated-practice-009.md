# Designing an Allowlist for User-Provided Expressions

## Objectives

When an application allows users to write or edit Spring Expression Language (SpEL), the expression becomes executable input. Users may try to read properties, call methods, access types, instantiate objects, or use other capabilities provided by the EvaluationContext. Therefore, an arbitrary SpEL string should never be evaluated directly with a full-privilege context.

An **allowlist** explicitly defines which constructs, data, and operations an expression is allowed to use. Secure design starts from the deny-by-default principle: allow only what has been explicitly defined and tested; any unapproved syntax or privilege is rejected.

After this lesson, you can:

- Design an allowlist for user-entered expressions.
- Choose an allowed subset of SpEL syntax and reject the rest.
- Restrict properties, methods, functions, and data that an expression can access.
- Configure an EvaluationContext with least privilege.
- Validate an expression before saving or activating it.
- Limit expression length, complexity, and evaluation resources.
- Isolate expressions by user, tenant, and policy version.
- Test both allowed syntax and prohibited access attempts.
- Monitor and revoke expressions when policies change.

## 1. Identifying the usage model before allowing SpEL

Before designing an allowlist, determine what users actually need to do. There are several levels of flexibility:

1. **Selecting a predefined rule:** users choose a predefined condition.
2. **Configuring parameters:** users enter thresholds, statuses, or value lists; the application binds the data into a fixed expression through variables.
3. **Building structured conditions:** users choose properties, operators, and values from a UI; the backend generates the expression from a validated model.
4. **Entering restricted free-form SpEL:** users enter an expression, and the backend parses and accepts only an approved subset of syntax.

The first three options are usually easier to control. If the business logic only needs users to pick fields, operators, and values, there is no need to open up a full expression language. Prefer structured configuration or fixed expression templates with context variables.

Only use user-provided SpEL when the flexibility benefit is large enough to justify maintaining parser policies, accessors, resolvers, tests, and revocation workflows.

## 2. The deny-by-default principle

An allowlist must state specifically what is allowed. Do not start by allowing all of SpEL and trying to block a few dangerous strings.

A policy can define the following categories:

| Category | Illustrative policy |
|---|---|
| Literal | Allow String, numbers, Boolean, and null if business logic needs them |
| Operators | Allow selected arithmetic, comparison, and logical operators |
| Parentheses | Allow grouping expressions with parentheses |
| Variables | Allow only the declared list of variables |
| Root object | Allow only a DTO with a clear schema |
| Properties | Allow only listed properties |
| Methods | Deny by default; open only approved pure methods |
| Functions | Open only specific functions with clear contracts, if truly needed |
| Collection operations | Allow selection/projection only with data bounds |
| Type reference | Deny |
| Constructor | Deny |
| Bean reference | Deny |
| Assignment | Deny |
| Class/reflection access | Deny |
| Side effects | Deny |

An actual policy can be narrower. For example, a simple filter might only need property reads, variables, literals, comparison operators, and logical operators. Do not enable collection operations, method invocations, or functions if there is no requirement for them.

Default rule: any node, property, or invocation not listed in the policy is treated as disallowed.

## 3. Restricting the EvaluationContext

EvaluationContext determines what data an expression can access and what operations it can perform. Do not use a broadly configured StandardEvaluationContext for untrusted expressions without a compelling reason and very strict controls.

**SimpleEvaluationContext** is designed for data binding scenarios with a restricted feature set. It does not support Java type references, constructor invocations, or bean references. This context also requires the application to explicitly choose how properties and methods are accessed.

Read-only context example:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .build();
~~~

This example illustrates read-only data binding mode. When a dedicated property allowlist is needed, configure a custom PropertyAccessor matching the allowed schema. When methods are needed, provide a custom MethodResolver that accepts only approved methods.

Do not enable general method invocation just to make an expression work. If using withInstanceMethods(), understand the full scope of methods that resolver can find; it does not automatically create a business-level allowlist.

For untrusted input, the context should:

- Provide only a normalized root DTO.
- Register only required variables.
- Provide only property-restricted PropertyAccessors.
- Provide an allowlist MethodResolver only if method invocation is required.
- Use a TypeConverter with explicit rules.
- Not register a BeanResolver unless needed.
- Not allow type or constructor access.
- Not put application contexts, service registries, or broad-privilege objects into variables.

SimpleEvaluationContext reduces the feature set, but does not replace the entire policy. Properties and methods exposed by the application itself must still be controlled.

## 4. Allowlisting properties via models and PropertyAccessors

Do not pass full entities or service objects as the root object. Entity getters may access lazy relationships, execute queries, return sensitive data, or run unexpected logic.

Create a read-only DTO containing only the exact data the expression needs:

~~~java
public record OrderRuleInput(
    BigDecimal total,
    String region,
    boolean active,
    OrderStatus status
) {}
~~~

The expression can read the published properties:

~~~text
#root.total >= #minimumTotal
and #root.active
and #root.region == #requiredRegion
~~~

A custom PropertyAccessor can verify the exact target type and allowed property names. If the expression requests a property not on the allowlist, the accessor denies access.

A property policy should specify:

- Accepted root types.
- Allowed property names.
- Data type of each property.
- Whether each property can be null.
- Which properties are allowed in collection operations.
- Which properties are prohibited because they contain secrets or broad-privilege objects.

Do not rely on users not knowing property names. Property names must be enforced at runtime using accessors and restricted input models.

## 5. Allowlisting methods and functions

Method invocation should be denied by default. A public method on an object is not automatically safe to invoke from an expression.

If a method is needed, the allowlist must specify:

- The owning class or interface.
- Method name.
- Parameter types and count.
- Return type.
- Null behavior.
- Purity and side effects.
- Execution cost limits.

For example, a pure status-checking method can be allowed:

~~~java
public final class RuleFunctions {

    private RuleFunctions() {}

    public static boolean isAllowedRegion(
            String region,
            Set<String> allowedRegions) {
        return region != null
            && allowedRegions.contains(region);
    }
}
~~~

Expose this method only if the policy needs it and arguments are validated. Do not let expressions call arbitrary methods by enabling broad reflective resolvers.

Methods that should be excluded from allowlists include:

- Writing data or mutating state.
- Sending emails, messages, or notifications.
- Calling HTTP, databases, or external systems.
- Reading/writing files, environment variables, or system properties.
- Spawning processes or threads.
- Accessing reflection, class loaders, or runtime.
- Accessing credentials, tokens, or secrets.
- Performing unbounded work.

Functions in SpEL are also a Java method execution capability. If functions are needed, register each approved function via the context mechanism appropriate for the Spring version in use, and test that the context cannot invoke methods outside the policy. Do not expose a broad shared set of functions to all tenants.

## 6. Denying type references, constructors, and bean references

The following syntaxes significantly expand an expression's capabilities:

~~~text
T(java.lang.Runtime)
new java.lang.String('value')
@someBean
~~~

In user-provided expressions, deny these capabilities by default:

- **T(...):** references Java classes, which can open paths to static fields and static methods.
- **new ...:** instantiates objects via constructors.
- **@beanName:** accesses Spring beans and can reach services or application resources.

Do not allow these syntaxes merely because a current class or bean looks harmless. The set of classes/beans can change as the application evolves and inadvertently open up more privileges.

If a rule needs a value from a bean or static constant, retrieve the value in Java and pass it into the context as a strongly typed variable. This ensures the expression only sees the necessary data rather than having the ability to look up objects in the container itself.

## 7. Inspecting syntax before evaluation

A safe workflow requires parsing and validation steps before evaluation. Do not immediately evaluate a user-submitted string.

A reference pipeline:

1. Verify the caller has permission to create or edit rules.
2. Check source length and encoding.
3. Parse using a fixed parser configuration.
4. Validate expression structure against the allowlist.
5. Verify referenced variables exist in the schema.
6. Verify properties and methods against the policy.
7. Check input types and expected return type.
8. Evaluate test cases with a restricted context.
9. Save the source, version, policy version, and author.
10. Activate the rule only after validation succeeds.

If you need to inspect expression structure, you can build a deny-by-default AST validator tied to a specific Spring version. The validator must recursively traverse every node, including nodes nested inside operators, function calls, collection operations, and subexpressions.

Do not use simple regexes to search for keywords such as new, T(, or @. Characters can appear inside string literals, nested expressions, or other syntaxes; regex cannot replace structural analysis. Succeeding at parsing also does not mean the expression is allowed.

AST APIs and node implementations can change across Spring versions. Version the validator, test it when upgrading the framework, and reject unrecognized nodes.

## 8. Allowlisting variables and input data types

Variables must be pre-declared according to a schema. For example:

| Variable name | Type | Required | Meaning |
|---|---|---|---|
| minimumTotal | BigDecimal | Yes | Minimum amount threshold |
| requiredStatus | OrderStatus | Yes | Required status |
| allowedRegions | Set<String> | No | Accepted regions |

Expressions may only reference variable names in the schema. If a non-existent variable is used, reject the rule at the validation step rather than waiting for a runtime error.

Before registering variables:

- Validate data types.
- Check nulls according to policy.
- Check value ranges.
- Bound collection and String sizes.
- Normalize enums, region codes, and formats.
- Do not pass secrets or broad-privilege objects.
- Do not take variable names from clients to construct dynamic access.

Example registering validated data:

~~~java
context.setVariable("minimumTotal", validatedMinimumTotal);
context.setVariable("requiredStatus", validatedStatus);
context.setVariable("allowedRegions", immutableAllowedRegions);
~~~

Use immutable collections or read-only copies if the expression does not need to mutate data. Do not share mutable objects across requests or tenants.

## 9. Limiting collection operations and complexity

Selection and projection are useful, but can process many elements or nest multiple levels:

~~~text
#root.orders.?[#this.total >= #minimumTotal].![#this.id]
~~~

If collections are large or expressions are deeply nested, costs can grow significantly. Define:

- Maximum collection size allowed in the context.
- Allowed depth of collection operations.
- Maximum number of nodes in the AST.
- Maximum expression nesting depth.
- Maximum String length and number of processable elements.
- Maximum concurrent evaluations.
- Execution cost of methods invoked inside predicates.

Do not allow methods that can load data from a database or call remote services in each loop iteration. Prepare required data before evaluation and pass it in a bounded DTO.

Consider denying user-written regex matches if patterns and inputs are not controlled. A regular expression with catastrophic backtracking can consume heavy CPU. If business logic requires pattern matching, restrict patterns and inputs or use a matching mechanism with suitable time characteristics.

SpEL does not provide a general execution timeout that makes arbitrary expressions safe. Length, node, collection, and concurrency limits are complementary control layers; if a hard deadline is needed for untrusted input, consider evaluating inside an isolated process or sandbox with resource limits.

## 10. Restricting the parser and compiler

Use a fixed, centrally managed parser configuration. Do not let users arbitrarily choose parser modes, class loaders, or options that alter expression capabilities.

For untrusted expressions:

- Keep the compiler OFF unless there is a specific reason, benchmark, and test coverage.
- Do not treat the compiler as a security control.
- Do not allow users to change the class loader.
- Do not enable auto-grow if rules do not need to create or expand data structures.
- Do not change parser configuration per client-supplied source.
- Record the Spring version and policy used to parse.

Compilation can depend on observed runtime types and does not support every expression construct. Enabling the compiler does not restrict properties, methods, or side effects; the allowlist must still be enforced independently.

## 11. Separating authorization from expressions

A syntax allowlist is not a business authorization mechanism. An expression may be restricted to read-only yet still return data the caller is not allowed to see if the root object contains too much information.

Authorization checks must be performed at the application layer:

- Does the caller have permission to create, edit, view, or activate the rule?
- Which tenant or module does the rule belong to?
- Does the caller have permission to evaluate that rule?
- Does the root object belong to the current tenant's scope?
- Are the passed variables allowed in that context?
- Is the result allowed to be returned to the caller?

Do not let the expression decide data access permissions by checking a variable controlled by the caller itself. The backend must verify tenant, user, and permissions before creating the context.

Use DTOs scoped by permissions and data visibility. If a caller may only view part of an Order, pass a DTO filtered to that data into the context instead of the full entity.

## 12. Error handling and user messages

Validation should reject disallowed expressions before activation. Messages shown to users should indicate the location and type of error at a helpful level, without leaking internal classes, stack traces, bean names, system structure, or sensitive data.

Errors can be categorized as:

- Invalid syntax.
- Node or operator not in allowlist.
- Undeclared variable.
- Disallowed property.
- Disallowed method/function.
- Invalid input type.
- Expression exceeds resource limits.
- Evaluation failed on current data.

In internal logs, record rule ID, version, policy version, message code, position, and cause class. Do not log the entire root object, sensitive variable values, or the source if the source might contain private data.

Do not automatically turn every error into false or null. An expression rejected by policy must be distinguished from a valid expression returning false.

## 13. Versioning policies and revoking privileges

Allowlists change over time. When adding properties, methods, or operators, older expressions might gain additional capabilities if evaluated under a new policy.

Version:

- Source expressions.
- Allowlist policies.
- Root DTO schemas.
- Function and method registries.
- Parser configuration.
- Spring Framework version.

Every evaluation should know which expression version and policy version apply. If a policy is narrowed, audit stored rules and reject or require edits for rules that are no longer valid.

When revocation is needed:

1. Disable the old rule or policy version.
2. Invalidate related parsed Expression caches.
3. Block new requests from using the revoked rule.
4. Record rejected evaluation attempts.
5. Re-run validation against the new policy.
6. Release the verified rule version.

Do not let caches retain expressions parsed or validated under an old policy and continue using them after privileges have been narrowed.

## 14. Caching and tenant isolation

If caching parsed Expressions, cache keys must include the source or source hash, rule version, parser configuration, and policy version. When the policy changes, old entries must be invalidated or separated by namespace.

For multi-tenant systems:

- Do not use cache keys based solely on rule name if tenants have different sources or policies.
- Verify rule access permissions before fetching entries from cache.
- Separate namespaces by tenant when needed.
- Do not store root objects, request variables, or EvaluationContexts in caches.
- Do not cache results unless all dependencies are identified.
- Use bounded caches to prevent continuous new sources from growing memory.

Expression caches store only parsed logic. Each evaluation must still create a context with the current caller's root object, variables, and data.

## 15. Example validation pipeline

A service can consolidate validation steps in one place:

~~~java
public ValidatedRule validate(
        String source,
        RulePolicy policy) {

    if (source == null || source.length() > policy.maxLength()) {
        throw new InvalidRuleException("Expression length is invalid");
    }

    Expression expression = parser.parseExpression(source);

    astAllowlistValidator.validate(expression, policy);

    variableSchemaValidator.validate(expression, policy.variables());

    return new ValidatedRule(
        expression,
        policy.version()
    );
}
~~~

This is an illustrative structure. `astAllowlistValidator` and `variableSchemaValidator` are application components that must be implemented, tested, and tied to a specific Spring version; the SpEL parser does not provide a complete allowlist policy on its own.

When evaluating:

~~~java
public Object evaluate(
        ValidatedRule rule,
        RuleInput input) {

    authorize(input.caller(), rule);

    SimpleEvaluationContext context =
        contextFactory.createReadOnlyContext(input);

    return rule.expression().getValue(context);
}
~~~

The context factory populates only allowed data. Authorization runs before evaluation and does not depend on the expression.

## 16. Testing the allowlist

The test suite should include both allowed expressions and rejected expressions. Testing only the happy path does not prove the policy is effective.

### Positive tests

- Approved literals and operators.
- Properties on the allowlist.
- Variables present in the schema.
- Approved methods or functions if allowed by policy.
- Selection/projection if allowed and data is within bounds.
- Root DTO of the right type.
- Result has the expected type.

### Negative tests

- Disallowed properties.
- Undeclared variables.
- Methods not in the registry.
- Invoking methods with side effects.
- Type references using T(...).
- Constructors using new.
- Bean references using @beanName.
- Assignments or state-mutating expressions.
- Accessing reflection, class loaders, runtime, or system properties.
- Collection operations exceeding limits.
- Regexes or inputs exceeding limits if pattern matching is restricted.
- Unrecognized AST nodes.
- Sources that are too long or too deeply nested.
- Callers without permission to use the rule or belonging to another tenant.

### Operational tests

- New policy version revokes old expressions.
- Cache does not serve entries validated under an old policy.
- Two tenants do not misuse each other's rules or cache entries.
- New contexts do not retain variables from previous requests.
- Validation errors do not trigger evaluation.
- Logs and error messages do not leak internal data.
- Upgrading Spring does not inadvertently expand the set of accepted nodes.

## 17. Allowlist implementation workflow

1. **Identify the need.** Check whether predefined rules, parameters, or structured builders can be used instead of free-form SpEL.
2. **Define the policy.** List allowed literals, operators, variables, properties, methods, and collection operations.
3. **Create the input DTO.** Include only necessary data already filtered by permissions.
4. **Configure a restricted context.** Prefer SimpleEvaluationContext and allowlisted accessors/resolvers.
5. **Parse and validate.** Use a deny-by-default AST policy tied to the specific Spring version.
6. **Verify the schema.** Confirm root type, variables, and result type.
7. **Apply resource limits.** Limit source, AST, collections, concurrency, and input size.
8. **Verify authorization.** Check caller, tenant, and permission to use the rule.
9. **Test.** Run positive, negative, boundary, concurrency, and tenant isolation tests.
10. **Version and release.** Store source, policy version, and audit metadata.
11. **Monitor and revoke.** Measure errors, evaluation time, and invalidate when policies change.

## 18. Best practices

- Prefer predefined rules, parameters, or structured builders over free-form SpEL.
- Use deny-by-default; enable only necessary syntax.
- Prefer SimpleEvaluationContext with restricted property access.
- Deny method invocation by default; if needed, use an allowlisted MethodResolver.
- Pass only read-only DTOs and validated variables.
- Deny type references, constructors, bean references, and assignments.
- Do not put services, repositories, ApplicationContext, or broad-privilege entities in root/variables.
- Do not allow methods with side effects or I/O.
- Use AST validation instead of regexes searching for dangerous strings.
- Tie the AST validator to the Spring version and reject unknown nodes.
- Limit source length, AST depth, collection size, and concurrency.
- Do not assume SpEL has a built-in execution timeout.
- Keep the compiler OFF unless specifically benchmarked and tested.
- Separate authorization from expressions.
- Version sources, policies, schemas, and parser configurations.
- Use bounded caches and invalidate when policies change.
- Record audit metadata without logging secrets or sensitive data.

## 19. Review checklist

Before allowing a user-provided expression to run in the application, check:

- [ ] Confirmed free-form SpEL is genuinely needed.
- [ ] Deny-by-default policy is defined and versioned.
- [ ] Allowed nodes, operators, and constructs have an explicit list.
- [ ] Root object is a restricted DTO, not a broad-privilege service/entity.
- [ ] Property access is restricted by an allowlist.
- [ ] Method invocation is denied by default or uses an allowlist resolver.
- [ ] Functions are published individually with clear contracts.
- [ ] Type references, constructors, bean references, and assignments are denied.
- [ ] Variables have schemas, types, null policies, and value ranges.
- [ ] AST is traversed recursively; unrecognized nodes are denied.
- [ ] Regex is not used in place of AST validation.
- [ ] Source, collections, AST, and concurrency have limits.
- [ ] No I/O or side-effecting methods exist in expressions.
- [ ] Authorization and tenant isolation are enforced at the application layer.
- [ ] EvaluationContext holds no excess data or privileges.
- [ ] Cache keys include source/version and policy/parser configuration.
- [ ] Policy changes revoke/invalidate old expressions.
- [ ] Positive, negative, boundary, and isolation tests exist.
- [ ] Logs and returned errors do not reveal internal data.

## Conclusion

User-provided expressions must be treated as executable input. A safe allowlist starts with deny-by-default, restricting syntax, properties, methods, and data; using a least-privilege EvaluationContext; parsing and validating the AST before evaluation; and separating authorization from expression logic. Prefer read-only DTOs, deny type references, constructors, bean references, and side effects, while bounding input size and complexity. Version policies, isolate tenants, manage caches, and test both allowed and rejected cases so the policy remains effective as the application and Spring Framework evolve.