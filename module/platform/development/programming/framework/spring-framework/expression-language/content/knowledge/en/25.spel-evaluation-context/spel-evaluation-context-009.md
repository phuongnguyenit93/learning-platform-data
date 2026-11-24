# Checking Access Permissions Before Running Expressions at Runtime

SpEL can evaluate expressions to check a business condition or an access policy. However, being able to parse an expression does not mean the caller is permitted to use that expression, nor does it mean the expression is safe to run in every EvaluationContext.

Before running an expression at runtime, an application must authenticate the caller, verify permission to use the policy, confirm that the expression comes from an approved source, and create an EvaluationContext containing only the necessary data and capabilities. When an expression is used to decide whether to allow an action, the result must be checked according to the fail-closed principle: missing data, evaluation errors, or non-Boolean results must never be treated as granting permission.

This lesson explains how to place an authorization gate before evaluation, how to separate permission to use an expression from the policy's result, how to restrict EvaluationContext, and how to integrate with Spring Security.

## 1. Objectives and prerequisites

After this lesson, you will be able to:

- Distinguish parsing an expression, authorizing expression usage, and evaluating an expression.
- Verify that the caller has permission to access a policy or resource before running the expression.
- Run only registered, verified, and approved expressions at runtime.
- Create a dedicated EvaluationContext per evaluation with data that the caller is permitted to access.
- Restrict root object, variables, PropertyAccessor, MethodResolver, TypeLocator, and BeanResolver.
- Require an explicit Boolean result and deny access when evaluation errors or returns null.
- Combine policy expressions with Spring Security method authorization.
- Avoid mistakenly caching access decisions across users, tenants, or resources.
- Test allowed paths, denied paths, and error cases.

You should be familiar with SpelExpressionParser, Expression, EvaluationContext, bean references, method invocation, and authentication/authorization concepts in Spring applications.

## 2. Three distinct steps: parse, authorize, and evaluate

A SpEL flow typically has three steps:

1. **Parse:** parses the string and creates an Expression. This step checks syntax and builds the expression structure.
2. **Authorize:** determines whether the caller is permitted to use that expression/policy on the requested data scope or resource.
3. **Evaluate:** executes the expression structure with the root object, variables, and resolvers in EvaluationContext.

These three steps answer three different questions:

| Step | Question |
|---|---|
| Parse | Is the string valid SpEL syntax? |
| Authorize | Does the caller have permission to use this policy in the current context? |
| Evaluate | Given the supplied data, what result does the policy condition return? |

Successful parsing does not prove an expression is safe. Evaluation returning true also does not by itself prove the caller has permission to access the policy or resource. The application must check permissions at the appropriate layer before allowing the expression to run.

For example, a user may have permission to read orders, yet lack permission to modify the policy governing order reads. Permission to use a policy and permission to perform a business action must be determined separately.

## 3. Authenticate the caller before processing expressions

First, the application needs to know who is sending the request. Authentication identifies the principal; authorization determines whether the principal is permitted to perform the action.

A typical flow:

~~~text
HTTP request
    |
    v
Authenticate principal
    |
    v
Check policy access permission
    |
    v
Check tenant and resource scope
    |
    v
Retrieve approved expression version
    |
    v
Create restricted EvaluationContext
    |
    v
Evaluate policy
    |
    v
Verify Boolean result
    |
    v
Allow or deny action
~~~

Do not take an expression sent by the client and evaluate it first to see whether the user is permitted. That reverses the trust boundary: an unauthorized expression runs before authorization completes.

If users are allowed to create or edit policies, that permission must also be checked separately at save/publish time. Someone with permission to execute an approved policy does not necessarily have permission to change the policy's content.

## 4. Verify permission to use a policy before evaluation

If an application stores multiple expressions in a database or configuration, manage them as policies with clear identifiers and statuses.

A policy should have at minimum:

- A stable ID.
- Tenant or ownership scope.
- Intended purpose, such as ORDER_READ or DISCOUNT_ELIGIBILITY.
- Expression content.
- Status: draft, approved, disabled, or revoked.
- Version or publication timestamp.
- Creator and approver according to the application workflow.

Before retrieving the content to evaluate, verify:

1. Does the caller have permission to request this kind of action?
2. Is the caller permitted to use policies belonging to the current tenant/scope?
3. Is the policy currently active and approved?
4. Does the policy match the exact use case type that the endpoint is executing?
5. Is the policy version still valid?
6. Does the target resource belong to a scope that the caller is permitted to access?

Do not rely solely on a policy ID sent by the client. The backend must determine the tenant, principal, and resource from trusted sources, then verify ownership/authorization relationships on the server side.

## 5. Use only approved expressions

There are three common sources of expressions:

| Source | Appropriate handling |
|---|---|
| Fixed expressions in source code | Review alongside code and version-control as application logic |
| Administrator-configured expressions | Follow a validate, review, approve, and publish workflow before runtime use |
| End-user-submitted expressions | Do not evaluate as general SpEL; use a restricted DSL or schema-validated filter |

If end users only need to select a field, operator, and value, define a constrained data structure. For example:

~~~json
{
  "field": "status",
  "operator": "EQ",
  "value": "ACTIVE"
}
~~~

The backend validates that the field is in an allowlist, the operator is in the supported set, and the value has the right type. The application then constructs the internal condition from the validated structure. This lets users customize filters without granting permission to write arbitrary SpEL syntax.

If administrators are permitted to write SpEL, store drafts separately, parse and validate against policy, run tests on sample data, require approval, and only then publish an immutable version for runtime.

Parsing only checks syntax. Do not use successful parsing as the sole criterion for publishing.

## 6. Create EvaluationContext after authorization succeeds

After authenticating the caller and policy, create the context from data that the caller is permitted to use.

Example of a DTO containing only data serving the decision:

~~~java
public record OrderPolicyInput(
    String status,
    BigDecimal total,
    boolean customerVerified
) {}
~~~

Expression:

~~~text
#input.status == 'PAID'
    and #input.total >= #minimum
    and #input.customerVerified
~~~

Context created for the evaluation:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .build();

context.setVariable("input", authorizedInput);
context.setVariable("minimum", minimum);
~~~

This example illustrates passing a verified DTO and variables into a read-only context. Confirm that the SpEL features required are compatible with SimpleEvaluationContext. If another capability is needed, add only that capability deliberately.

Do not pass an entire entity graph, ApplicationContext, BeanFactory, repository, or administrative service as the root object. A small DTO ensures expressions only see necessary fields and reduces the risk of reading out-of-scope data.

## 7. Restricting EvaluationContext capabilities

EvaluationContext does not just hold variables. It also determines how expressions access properties, invoke methods, locate types, create objects, and reference beans.

| Capability | What must be decided |
|---|---|
| PropertyAccessor | Which properties can be read or written? |
| MethodResolver | Which methods are permitted to be invoked? |
| TypeLocator | Is T(...) needed and which classes may be referenced? |
| ConstructorResolver | Is the new syntax needed? |
| BeanResolver | Is @beanName needed and which beans are exposed? |
| Variables/functions | Which data and functions are placed into the context? |
| Parser configuration | Are assignment/auto-grow or object-mutating features enabled? |

For read-only policies, prefer:

- A small root DTO or strongly typed variables.
- Read-only property access.
- No bean references if unnecessary.
- No type references or constructor invocations if unnecessary.
- No exposing methods with side effects.
- Registering only pure, controlled functions if the use case genuinely needs them.
- Disabling auto-grow if the expression is only used for reading/checking.
- Not placing shared mutable objects into the context if the expression could modify them.

SimpleEvaluationContext is generally well suited for restricted data-binding use cases. StandardEvaluationContext is more flexible and must be carefully configured when used for runtime policies. Do not treat merely picking a context class as a safety guarantee; registered objects and capabilities still determine the access scope.

## 8. Checking results according to the fail-closed principle

If an expression decides whether to allow an action, only Boolean `true` should be treated as passing the policy.

Example:

~~~java
Object result = expression.getValue(context);

if (!(result instanceof Boolean allowed)) {
    throw new AccessDeniedException(
        "Policy did not return a Boolean result"
    );
}

if (!allowed) {
    throw new AccessDeniedException("Policy denied the action");
}
~~~

This handling rejects the following cases:

- Result is false.
- Result is null.
- Result is a String, Number, or other object.
- Evaluation throws an exception.
- Required variable or property does not exist.
- Conversion or method invocation fails.

Do not coerce an arbitrary value to Boolean just to make an expression appear to work. Policies must have an explicit result contract.

Fail-closed means errors or insufficient data must not be interpreted as permission. If a policy cannot be evaluated, the application should deny access or return an appropriate operational error while recording the cause on the server side.

## 9. Example of a pre-runtime check flow

The following code illustrates the processing structure. The repository and authorization service are application-defined components:

~~~java
public boolean evaluatePolicy(
        Authentication caller,
        String policyId,
        OrderPolicyInput input) {

    PolicyDefinition policy =
        policyRepository.findActive(policyId)
            .orElseThrow(() ->
                new AccessDeniedException("Policy unavailable"));

    authorizationService.requireCanExecute(
        caller, policy.getTenantId(), policy.getPurpose());

    if (!policy.isApproved()) {
        throw new AccessDeniedException("Policy is not approved");
    }

    if (!"ORDER_READ".equals(policy.getPurpose())) {
        throw new AccessDeniedException("Policy purpose mismatch");
    }

    Expression expression =
        parser.parseExpression(policy.getExpression());

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("input", input);

    Object result = expression.getValue(context);

    if (!(result instanceof Boolean allowed)) {
        throw new AccessDeniedException("Invalid policy result");
    }

    return allowed;
}
~~~

Key points of the example:

1. The backend retrieves the policy from an application-managed source.
2. Authorization verifies principal, tenant, and purpose before evaluating.
3. Only an approved policy is allowed to run.
4. The context is created separately and contains only the necessary input.
5. The result must be a Boolean.
6. The caller proceeds with the action only when the policy permits it and all other permission checks also succeed.

In production, parse/validate policies upon publishing and store the approved version. Runtime must still verify the caller's permissions on every request; never skip authorization just because the expression was already parsed or cached.

## 10. Combining with Spring Security method authorization

Spring Security provides method security annotations such as `@PreAuthorize`. They check conditions before a method is invoked via the method security interceptor.

Example:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ') and @orderAccessPolicy.canRead(#orderId)")
public Order readOrder(Long orderId) {
    return orderService.findById(orderId);
}
~~~

In the example:

- `hasAuthority` checks the caller's authority.
- `@orderAccessPolicy` references a Spring-managed policy bean.
- `canRead` checks whether the caller has permission to read that specific order.
- The `readOrder` method is invoked only when the expression permits it.

Method security must be enabled and Spring Security's expression context must be properly configured. Policy beans should perform read-only checks with clear inputs and without mutating state themselves.

Do not confuse `@PreAuthorize` with `@PostAuthorize`. `@PreAuthorize` checks before the method executes; `@PostAuthorize` checks after the method has run and is typically used to decide whether to return the result. If the requirement is to prevent an action from occurring without permission, place the check before the method or service operation.

A standalone SpEL expression using StandardEvaluationContext does not automatically possess Spring Security's `hasAuthority` helper or security root object. Those helpers exist only in the corresponding integrated context.

## 11. Separating permission to access a policy from the policy result

Suppose a policy has the content:

~~~text
#input.total < 500
~~~

A `true` result only states that the condition `total < 500` holds for the current input. It does not prove that the caller is permitted to read the policy, access the order, or perform another action.

Separate the layers:

- **Permission to use policy:** is the caller allowed to use this policy?
- **Permission to access data:** is the caller allowed to view the data placed into the context?
- **Policy result:** does the data satisfy the condition in the expression?
- **Permission to perform action:** does the caller have sufficient permission to execute the final action?

Depending on the use case, the policy result can serve as an additional condition for authorization, but it does not replace access permissions determined at the security layer.

For example, a caller with authority `ORDER_READ` who does not belong to the order's tenant must still be denied, even if the expression returns `true`. Input data must also not be loaded or placed into the context before access scope is confirmed.

## 12. Preventing cross-tenant and cross-resource access

In multi-tenant applications, every step of retrieving policies and data must bind the tenant from a trusted source.

Principles:

1. Obtain the current tenant from the authenticated principal or security context.
2. Verify the policy belongs to that tenant before reading the expression content.
3. Verify the resource belongs to the tenant/scope accessible to the caller.
4. Place only permitted fields into the expression's DTO.
5. Do not accept a `tenantId` in the request as proof of access permission.
6. Do not reuse contexts or authorization results across tenants.
7. Record policy ID, version, tenant, and decision code in audit logs according to data policy.

If a policy is shared system-wide, explicitly represent the global scope in the model and authorization. Do not infer a global policy merely from the absence of a `tenantId`.

## 13. Avoiding TOCTOU between check and action

TOCTOU is a situation where resource state changes after a permission check but before the action is executed.

Example:

1. The application verifies the caller has permission to edit an order.
2. Another process changes the order's owner or status.
3. The application proceeds to write based on the stale decision.

For sensitive operations, bind the check to the actual operation:

- Re-read or lock the resource within an appropriate transaction.
- Verify permissions against the current state.
- Perform the update within the same transaction when possible.
- Use optimistic locking or version checks if data can change concurrently.
- Do not treat an expression result computed from stale data as permanent authorization.

An expression should evaluate a verified data snapshot for a single operation. If critical state changes before writing, re-verify according to business policy.

## 14. Expression caching vs. caching access decisions

Parsed Expressions can be cached to avoid re-parsing the same content. However, caching expressions and caching authorization decisions are two separate issues.

**Caching parsed Expressions:**

- Can use a key consisting of policy ID, version, and parser configuration.
- Cache only approved policy versions.
- When a policy is revoked or changes version, invalidate the cache appropriately.
- Each evaluation must still create a context with the current caller's data and permissions.

**Caching authorization results:**

- Can become incorrect if the principal, role, tenant, resource owner, or policy status changes.
- If caching is genuinely needed, the key must reflect all relevant security factors and have an explicit expiration/invalidation policy.
- Do not use a `true` result for one user to decide for another user.
- Do not use a result for one resource to decide for another resource.

The safe default is to cache the parsed expression structure while re-executing authorization and policy evaluation in the current context.

## 15. Exception handling and audit logging

Errors can occur before or during evaluation:

- Caller lacks authority.
- Policy does not exist, is disabled, or is not approved.
- Policy belongs to another tenant.
- Expression fails to parse.
- Required variable or property does not exist.
- Method or type is not permitted to be accessed.
- Type conversion fails.
- Expression returns null or a non-Boolean type.
- A method inside the expression throws an exception.

The application should classify errors:

| Error type | Handling |
|---|---|
| Unauthorized | Deny access |
| Invalid or unapproved policy | Do not evaluate |
| Syntax error in published policy | Halt processing, report configuration error |
| Runtime error during evaluation | Fail closed and record the error |
| False result | Deny according to policy |
| Non-Boolean result | Deny due to policy contract violation |

Audit logs should record necessary metadata such as caller ID, tenant, action, resource ID, policy ID/version, decision, and error code. Do not log tokens, secrets, entire objects, or expressions that may contain sensitive data without justification and an appropriate retention policy.

Information returned to the client should be sufficient to indicate denial without exposing internal structure, private expressions, or stack trace details.

## 16. Testing the authorization gate

The test suite should verify that permissions are checked before evaluation:

| Case | Expected outcome |
|---|---|
| Authorized caller, approved policy, expression true | Allowed per policy |
| Caller lacks permission to use policy | Denied before evaluation |
| Policy belongs to another tenant | Denied, no out-of-scope data loaded |
| Draft or disabled policy | Not evaluated |
| Policy purpose mismatch | Denied |
| Expression parse error | Action not performed |
| Expression returns false | Denied |
| Expression returns null | Denied |
| Expression returns String or Number | Denied for violating contract |
| Evaluation throws exception | Fail closed |
| Required variable missing | Denied or data error reported |
| Policy version revoked | Stale cached version not used |
| Two different callers | Do not share context or decision |
| Two different tenants | No cross-mixing of data or results |
| Resource changes before write | Re-checked via transaction/version |

An important test is verifying that the expression evaluator is not called when the authorization service denies access. You can use a mock or spy in tests to count evaluation invocations. When the caller is unauthorized, the evaluation count must be 0.

## 17. Common mistakes and troubleshooting

| Symptom | Common cause | How to resolve |
|---|---|---|
| Parse succeeds yet caller should not run expression | Confusing valid syntax with permission to use | Place an authorization gate before evaluation |
| Users can submit arbitrary expressions | Trusting client input as an approved policy | Use a policy registry or restricted DSL |
| Policy true yet resource access is still unauthorized | Using policy result in place of authorization | Independently check principal, tenant, and resource permissions |
| Caller lacks permission yet expression still runs | Evaluating before checking permissions | Reorder the processing flow and test evaluate count |
| Expression reads out-of-scope data | Root object or beans too broad | Use small DTOs and a restricted context |
| Null result interpreted as permitted | Missing explicit Boolean type check | Fail closed on null and non-Boolean types |
| Stale policy continues to be used | Cache not keyed by version or not invalidated | Cache by version and check active status |
| Data across requests gets mixed | Sharing mutable EvaluationContext | Create a dedicated context per evaluation |
| Permissions change between check and write | TOCTOU | Re-check within transaction or use versioning |

## 18. Practice exercises

1. Create a fixed policy `#input.total >= #minimum` and evaluate it using a DTO and a read-only context.
2. Create a service that checks whether the caller has permission to use a policy ID before calling `Expression.getValue()`.
3. Write a test confirming that when authorization fails, the evaluator is not invoked.
4. Test policies in draft, approved, disabled, and revoked states.
5. Create two tenants with two policies having the same display name but different IDs/scopes; verify there is no cross-access.
6. Test expressions returning false, null, String, and Boolean to verify fail-closed behavior.
7. Integrate `@PreAuthorize` for a service method and verify the method does not run when denied.
8. Cache parsed Expressions by policy version while creating a new EvaluationContext for each request.
9. Simulate changing resource state between the authorization check and the update; determine how transaction/version checks protect it.
10. Record audit metadata for allow/deny decisions without logging secrets.

## 19. Checklist before running expressions at runtime

- [ ] Has the caller been authenticated?
- [ ] Was permission to use the policy checked before evaluation?
- [ ] Does the policy match the tenant, purpose, and resource scope?
- [ ] Does the expression come from a trusted source and has it been approved?
- [ ] Does the policy have a clear version and active status?
- [ ] Is the caller permitted to access the data placed into the context?
- [ ] Do the root object/variables contain only necessary data?
- [ ] Does EvaluationContext restrict property, method, type, constructor, and bean access?
- [ ] Are arbitrary expressions submitted by end users avoided?
- [ ] Is the result required to be Boolean true before allowing?
- [ ] Are null, exceptions, and wrong result types rejected?
- [ ] Is authorization re-performed if resource state changes?
- [ ] Does caching separate parsed expressions from authorization decisions?
- [ ] Is there a test confirming the evaluator does not run when the caller is denied?
- [ ] Do audit logs capture sufficient metadata without leaking sensitive data?

## 20. Conclusion

Before running an expression at runtime, the application must authenticate the caller, verify permission to use the policy and resource scope, and only then create a restricted context to evaluate. Successful parsing is not authorization; a `true` expression result also does not replace application-layer access control. Run only approved policies, provide necessary DTOs and variables, restrict resolvers/accessors, require a Boolean result, and fail closed on errors. For sensitive actions, bind permission checks to the actual operation to avoid TOCTOU, while caching expression structures separately from authorization decisions.