# Restricting Root Object, Property Accessors, and Resolvers

SpEL can read properties, invoke methods, reference types, access beans, and call functions depending on the capabilities provided by the EvaluationContext. Therefore, the security of an expression does not depend solely on the expression string. It also depends on the root object, property accessors, method resolvers, type locator, bean resolver, registered functions, and write permissions in the context.

When expressions are written and fully controlled in source code, their usage scope is usually reviewed alongside the application. When an expression comes from a database, editable configuration file, or user, treat it as executable input. Secure design begins with the principle of granting only the minimal data and minimal capabilities required by the use case.

## 1. EvaluationContext Is the Access Boundary

EvaluationContext provides the data and mechanisms SpEL uses to resolve an expression. A context can contain a root object, variables, property accessors, method resolvers, a type locator, a bean resolver, functions, and a type converter.

Each component opens another way for an expression to reach into the application:

| Component | Capability Provided |
|---|---|
| Root object | Data and methods on the root object |
| Context variables | Named objects or values |
| PropertyAccessor | Reading or writing properties on objects |
| MethodResolver | Finding and invoking methods |
| TypeLocator | Resolving types in `T(...)` |
| BeanResolver | Looking up beans using `@beanName` syntax |
| Registered functions | Calling registered `Method`s by function name |
| TypeConverter | Converting types during evaluation or assignment |

Not every expression needs all of these capabilities. A rule that only reads two properties to decide display visibility may not need method invocation, type references, bean references, or write access.

Configure the context according to the specific use case. The fewer objects and resolvers granted, the easier it is to reason about what an expression can do.

## 2. Choose a Small, Well-Scoped Root Object

The root object is the starting point of an expression. Passing a large entity or a service with many methods as the root allows the expression to access more data and behavior than necessary.

For example, instead of passing an entire User entity into the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(user);
~~~

consider creating a DTO containing only the data needed for the rule:

~~~java
public record UserRuleData(
        String region,
        boolean active,
        int accountAgeDays) {
}

UserRuleData ruleData = new UserRuleData(
        user.getRegion(),
        user.isActive(),
        user.getAccountAgeDays()
);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Then pass `ruleData` as the root object during evaluation:

~~~java
Expression expression = parser.parseExpression(
        "active and region == 'APAC' and accountAgeDays >= 30"
);

Boolean allowed = expression.getValue(
        context,
        ruleData,
        Boolean.class
);
~~~

A small DTO limits the data visible to the expression. It also decouples the rule structure from persistence entities and avoids accidentally exposing lazy relationships, secrets, or business methods.

The root object should reflect the exact contract of the expression. If a rule only needs three values, there is no need to place the entire object graph into the context.

## 3. Do Not Pass Services or Repositories as the Root Object

Services and repositories often have many methods, dependencies, and side effects. If a service is set as the root object in a context with method invocation capabilities, an expression can invoke operations that the initial configuration did not intend to permit.

For example, do not use a broadly privileged service as the root:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(paymentService);
~~~

An expression can attempt to invoke methods on this object if the MethodResolver allows it.

If a value computed by a service is needed, invoke the service in Java first, and then pass only the required result into the context:

~~~java
boolean eligible = eligibilityService.isEligible(customer);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

context.setVariable("eligible", eligible);
~~~

The expression only receives the resolved Boolean. It does not need access to `eligibilityService` or the service's internal dependencies.

This approach keeps system access in the application layer, where authorization, transactions, logging, and error handling can be performed explicitly.

## 4. Use SimpleEvaluationContext When Only Data Binding Is Needed

SimpleEvaluationContext is designed for SpEL scenarios with a restricted feature scope. It does not provide the full capabilities of StandardEvaluationContext.

Example of a read-only property data binding context:

~~~java
EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

If writing properties is needed:

~~~java
EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

SimpleEvaluationContext does not support type references, constructor invocation, or bean references like the full context does. Instance method invocation is also disabled by default; the builder can enable it explicitly if the use case truly requires it.

For read-only rules, start with a read-only context. Only choose read-write when properties must be updated, and only enable instance methods once you have clearly identified which methods are needed.

Do not switch to StandardEvaluationContext merely because a simple expression hits a limitation. First check whether the data can be prepared in Java or a smaller context can be provided.

## 5. Distinguishing StandardEvaluationContext and SimpleEvaluationContext

StandardEvaluationContext provides a broader set of capabilities, including configurable reflection mechanisms and resolvers. This is useful for internal expressions needing many SpEL features, but it also widens the access scope if used with untrusted expressions.

SimpleEvaluationContext is suitable for data binding and an explicitly selected subset of features. It does not automatically become a sandbox for all scenarios, but it reduces the capabilities available by default.

| Need | Configuration Direction |
|---|---|
| Read JavaBean properties only | Read-only SimpleEvaluationContext |
| Controlled reading and writing of properties | Read-write SimpleEvaluationContext |
| Instance methods needed | Enable explicitly only if truly required |
| Type references, constructors, or bean references needed | Carefully evaluate the need and scope of StandardEvaluationContext |
| User-supplied expressions | Do not grant a broad context; use a DSL or structured rules if possible |

Choose the context based on the capabilities the expression needs, not simply on which context is easier to construct.

## 6. PropertyAccessor Determines Which Properties Can Be Read or Written

PropertyAccessor is the mechanism SpEL uses to read and write properties on objects. An accessor can support a specific object type and decide which properties may be accessed.

StandardEvaluationContext can be configured with PropertyAccessors. SimpleEvaluationContext also allows building a context from a selected set of accessors.

For sensitive data, do not expose every property simply because an object has getters. For example, an Account might have public properties `balance`, `status`, `passwordHash`, and `internalFlags`. A display rule might only need `status` and `region`; exposing all properties is unnecessary.

An allowlisted accessor can permit only predefined properties. Example target contract:

~~~text
UserRuleData.region       read
UserRuleData.active       read
UserRuleData.accountAgeDays read
UserRuleData.internalNotes deny
UserRuleData.credential   deny
~~~

This is a design principle. When implementing a custom PropertyAccessor, clearly define the target type, allowed property names, how reads work, how writes work, and the exception thrown when a property is unsupported.

Do not use a general-purpose accessor that can read any field or invoke reflection arbitrarily on any object if the expression is untrusted.

## 7. DataBindingPropertyAccessor and Access Scope

Spring provides `DataBindingPropertyAccessor` for data binding use cases. SimpleEvaluationContext has builders for read-only or read-write data binding to create contexts with the corresponding property accessor.

The data binding accessor restricts certain technical access patterns compared to broad reflective property access. Even so, whether a property can be read still depends on the provided object and that object's property contract.

Remember that an accessor cannot automatically turn an overly broad root object into a safe business API. If the root object has many public properties, consider using a DTO or a custom accessor to reduce the access surface.

For read-only data, do not enable write permissions. For data that must be updated, predefine which properties can be modified and validate the object after writing.

## 8. Building an Allowlisted PropertyAccessor

If a rule is only allowed to read certain properties, you can implement a specialized PropertyAccessor for that DTO type. The accessor should perform these steps:

1. Declare the target type supported by the accessor.
2. Check that the property name is in the allowlist.
3. Read values only from the API defined for that property.
4. Reject properties outside the list.
5. Disallow writes if the use case is read-only.
6. If writes are allowed, separately check the list of writable properties and value types.

Design-level allowlist example:

~~~java
Set<String> readableProperties = Set.of(
        "region",
        "active",
        "accountAgeDays"
);

Set<String> writableProperties = Set.of();
~~~

An empty writable set represents a read-only accessor. If writing is required, explicitly declare each permitted property and verify permissions at the application layer before calling `setValue`.

When an accessor does not support a property, let the resolver proceed according to the designed policy or throw an appropriate error. Do not silently return `null` for forbidden properties, as that can cause the expression to misinterpret the data as actually being `null`.

## 9. MethodResolver Controls Method Calls

MethodResolver is responsible for locating a matching method for an invocation in an expression. StandardEvaluationContext has a broader reflective method resolution mechanism by default.

If an expression only needs to read properties, do not permit method invocation. If calling methods is necessary, restrict the exposed API using a small root object or a custom resolver that allows only selected methods.

Example of a DTO providing only pure methods:

~~~java
public class ProductRuleData {

    private final int stock;
    private final boolean discontinued;

    public ProductRuleData(int stock, boolean discontinued) {
        this.stock = stock;
        this.discontinued = discontinued;
    }

    public boolean isAvailable() {
        return stock > 0 && !discontinued;
    }
}
~~~

An expression can check `isAvailable` if the context allows instance methods. However, do not pass an object with methods that write data, send requests, or delete data into the context just to use one utility method.

When methods are not needed, use SimpleEvaluationContext with instance method invocation disabled. If methods are needed, prefer small, pure APIs with names that clearly describe the result.

## 10. TypeLocator and T(...) Type References

TypeLocator resolves type names referenced with the `T(...)` syntax. When using StandardEvaluationContext, the default StandardTypeLocator can resolve types by fully qualified name and imported packages.

Type references can open the door to static methods or static fields:

~~~text
T(java.lang.Math).max(10, 20)
T(java.util.UUID).randomUUID()
~~~

If an expression does not need type references, avoid granting this capability. SimpleEvaluationContext does not provide type references like StandardEvaluationContext.

If the application must support a set of types, consider a TypeLocator that restricts the list of allowed classes. Do not let expressions arbitrarily resolve every class on the classpath just to support a few calculations.

A safe type reference can still invoke a static method with side effects if that method is permitted. Therefore, controlling TypeLocator must go hand in hand with controlling method resolution and other objects in the context.

## 11. BeanResolver and Spring Bean Access

BeanResolver allows SpEL to reference beans by name using `@beanName` syntax. When an appropriate BeanResolver is present, an expression can look up a bean and access properties or invoke methods on it.

Examples:

~~~text
@featureSettings.enabled
@priceCalculator.calculate(#amount)
~~~

This capability can couple expressions to many services in the ApplicationContext. If expressions are edited by untrusted sources, bean references can open access beyond the rule's intended scope.

Do not configure a BeanResolver if the use case does not require bean references. If needed, expose only a small façade; do not bring the entire service container or beans with broad write privileges into the expression scope.

For Spring Boot configuration conditions, avoid referencing business beans in `@ConditionalOnExpression` because conditions are evaluated early during configuration processing and can trigger premature bean initialization.

## 12. Registered Functions Are Also an Access Surface

Functions registered in an EvaluationContext can be invoked from an expression using `#functionName(...)`. Each function opens another action that the expression can execute.

Register only truly necessary functions. Prefer pure methods that take explicit data and return deterministic results.

Do not register functions such as:

~~~text
#deleteAccount(...)
#sendPayment(...)
#executeCommand(...)
~~~

for a context evaluating untrusted rules.

If a domain check is needed, provide a narrowly scoped read-only function, such as `#isEligible(#ruleData)`. Authorization checks and side effects remain in the service layer.

A function does not become safe simply because its name is not shown to the user. Any function present in the context is a capability an expression can attempt to invoke.

## 13. Write Permissions and Assignment

SpEL can assign values to properties or indexers if the context and accessor permit writes. This is useful for data binding, but unnecessary for filtering or calculation expressions.

If an expression does not need to modify objects, use a read-only context or disable assignment via the appropriate builder configuration. Do not grant a read-write context simply because it can also read properties.

When writes are necessary, restrict the root object to a DTO or command object containing the updatable properties. Do not put an entity with sensitive state into the context and let the expression choose arbitrary property paths.

After updating, the application still needs to validate the object, check permissions, and decide whether to persist changes. A successful write through PropertyAccessor does not mean the operation is permitted by business rules.

## 14. Do Not Evaluate Arbitrary User-Submitted Expressions

User-supplied expressions can contain far more syntax than a simple business condition. If evaluated directly with a broad context, users can try reading out-of-scope properties, calling methods, or referencing granted beans/types.

Safer alternatives:

- Provide a structured DSL, such as allowlisted fields, operators, and values.
- Let users choose from predefined rule templates.
- Parse input into an AST or custom data structure and evaluate the permitted operations yourself.
- If SpEL is still used, constrain syntax, context, root object, accessors, and resolvers under an explicit contract.
- Disallow arbitrary expressions from performing assignments or calling methods with side effects.

A simple field allowlist in the UI is insufficient if the backend still evaluates arbitrary SpEL strings with a full context. Enforcement must occur on the server side before evaluation.

## 15. Separating Data and Business Logic from Expressions

Expressions should focus on small calculations or conditions. Operations such as authorization checks, database queries, API calls, multi-rule pricing, and state updates belong in Java.

For example, instead of letting an expression call multiple services:

~~~text
@accountService.isActive(#userId) and
@riskService.score(#userId) < 50 and
@paymentService.hasNoDebt(#userId)
~~~

compute a result DTO in the service:

~~~java
public record EligibilityRuleData(
        boolean active,
        int riskScore,
        boolean hasNoDebt) {
}
~~~

The service prepares the data after performing appropriate authorized checks. SpEL only evaluates:

~~~text
active and riskScore < 50 and hasNoDebt
~~~

This prevents expressions from directly orchestrating services. Input data can also be tested independently without exposing internal application dependencies.

## 16. Limiting Expression Cost and Complexity

Expressions can iterate over collections, call methods, and access nested objects. Even a short expression can incur high cost if it calls a database-querying method for each element or iterates over a huge collection.

Some principles:

1. Limit the size of data placed into the context.
2. Avoid methods with I/O or lazy loading inside predicates.
3. Precompute required data in Java.
4. Keep collection operations simple and clearly bounded.
5. Do not let users supply expressions that can construct unbounded computational structures.
6. Monitor evaluation duration and function/method call counts on critical rules.

If a large dataset must be queried, filter at the database or service layer instead of loading the entire collection into the context and letting SpEL iterate over it.

## 17. Checking and Handling Errors at Boundaries

When an expression is rejected or fails evaluation, distinguish syntax errors, resolution errors, and runtime errors:

| Error Category | Example | Handling Direction |
|---|---|---|
| Parse | Invalid syntax | Check grammar and templates |
| Property access | Property not in allowlist or does not exist | Check accessor and root object |
| Method resolution | Method not permitted or does not exist | Check MethodResolver |
| Type resolution | `T(...)` references a disallowed type | Check TypeLocator |
| Bean resolution | `@beanName` cannot be resolved | Check BeanResolver and bean policy |
| Conversion | Argument/value type mismatch | Check TypeConverter |
| Assignment | Expression attempts to write in a read-only context | Reject write operation |
| Runtime | Getter or method throws an exception | Inspect cause and handle at application layer |

Do not return `true` or `null` by default when an expression errors. For rules governing critical permissions or state, evaluation failures should be handled with a fail-closed policy appropriate to the use case.

Logs should record the rule ID, error category, and necessary technical cause. Avoid logging the full expression or sensitive data if that string may contain user information.

## 18. Testing Access Control Configurations

A secure context must be tested for both permitted and denied capabilities.

Cases to test:

- Expression can read allowlisted properties.
- Expression cannot read sensitive properties.
- Expression cannot write properties in a read-only context.
- Read-write context only updates permitted properties.
- Method invocation is rejected when disabled.
- Methods not in the allowlist cannot be called.
- Type references are rejected if unsupported by the context or restricted by TypeLocator.
- Bean references are not resolved if no BeanResolver is configured.
- Functions outside the list do not exist in the context.
- Nulls and mistyped data are handled according to policy.
- Failing expressions are not turned into default-allow results.

Test against the exact EvaluationContext and resolvers deployed by the application. Unit tests that only parse expressions without evaluating them against the real context will not verify access boundaries.

## 19. Complete Example: Read-Only Context with Minimal Data

The following example creates an object containing only the data the rule needs:

~~~java
public record OrderRuleData(
        BigDecimal total,
        String region,
        boolean customerActive) {
}
~~~

Prepare the data in Java and evaluate:

~~~java
OrderRuleData data = new OrderRuleData(
        new BigDecimal("250.00"),
        "APAC",
        true
);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression = parser.parseExpression(
        "total >= 100 and region == 'APAC' and customerActive"
);

Boolean accepted = expression.getValue(
        context,
        data,
        Boolean.class
);
~~~

The expression only reads three properties. It has no services, repositories, bean resolvers, or type references needed for this operation.

If the rule later needs another value, extend the DTO intentionally according to contract. Do not pass an entire entity or ApplicationContext just to avoid preparing data.

## 20. Summary

Restricting SpEL starts with the EvaluationContext. Choose a small root object, prefer DTOs containing only the necessary data, use SimpleEvaluationContext where appropriate, and grant only the property accessors, method resolvers, type locators, bean resolvers, or functions the use case truly requires.

PropertyAccessor determines which properties can be read/written; MethodResolver determines which methods can be invoked; TypeLocator resolves `T(...)`; BeanResolver resolves `@beanName`; registered functions expose additional callable actions. Assignment permissions must also be restricted if the expression is read-only.

Do not evaluate arbitrary user-supplied expressions with a broad context. Use structured DSLs or rule templates when possible, move business logic and side effects into Java, test both allowed and denied cases, and handle errors according to clear policies. A secure context exposes only the exact data and behaviors needed for a specific purpose.