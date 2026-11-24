# Building Contexts per Use Case Instead of Using an All-Powerful Context

EvaluationContext determines what data SpEL can see and which operations it can perform when evaluating an expression. A context can provide a root object, variables, functions, property accessors, method resolvers, constructor resolvers, TypeLocator, and bean resolvers. The broader the configuration, the more flexible the expression becomes, but the larger the blast radius and risk as well.

Therefore, an application should build contexts per use case. Rules that only read attributes should use a read-only context; rules that need a few method calls should enable only permitted methods; expressions needing type references or constructors must have a dedicated context with explicit restrictions. Do not use a single high-privilege StandardEvaluationContext for every kind of expression just because it is convenient to instantiate.

## 1. EvaluationContext is the boundary between the expression and the application

SpEL does not inherently know which business objects are permitted to be accessed. The application provides the evaluation environment through EvaluationContext.

A context can contain or control:

- Root object: the base object from which unprefixed property paths start reading.
- Variables: values referenced with the `#` prefix.
- Functions: Methods registered for expressions to invoke using function syntax.
- PropertyAccessors: how properties are read or written on objects.
- MethodResolvers: how methods are found and invoked.
- ConstructorResolvers: how constructors are found and invoked.
- TypeLocator: how class names are resolved in `T(...)`.
- BeanResolver: how expressions reference beans by name.

Not every use case needs all of these capabilities. For example, an expression that only checks order.total may only need a root object and property read permission. It does not need to create new objects, call services, access beans, or invoke arbitrary methods.

Treat the context as a contract for what an expression is permitted to do. When the contract is clearly designed, rules are easier to understand and easier to control.

## 2. Distinguishing StandardEvaluationContext and SimpleEvaluationContext

Spring provides two commonly used options with different feature levels.

### StandardEvaluationContext

StandardEvaluationContext provides a broad set of SpEL capabilities. Under its default configuration, it includes reflective mechanisms to access properties, invoke methods, and create objects; it also uses StandardTypeLocator to resolve type references. Applications can register variables, functions, resolvers, and custom components.

Initialization example:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

This context is appropriate when an expression genuinely needs advanced features, but it must be configured deliberately. If you put a high-privilege object as the root or allow broad method invocation, expressions can affect more parts of the application than intended.

Bean references do not appear automatically just by using StandardEvaluationContext; the application must configure a BeanResolver if it wants to support bean references. Even so, the default reflective capabilities are already broad enough to warrant careful review of the expression source and the supplied object graph.

### SimpleEvaluationContext

SimpleEvaluationContext is designed for a more restricted subset of SpEL, typically suited to data-access rules. Its builder lets you choose a property access mode and optionally enable instance method access when a use case needs it.

Read-only data example:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

If instance methods need to be permitted for a specific need:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .withInstanceMethods()
                    .build();

SimpleEvaluationContext does not support type references, constructor references, or bean references by default. Thus, it is an appropriate choice when expressions only need to read data and perform a limited set of operations. Check the exact builder options that the use case needs instead of enabling extra capabilities out of habit.

## 3. Start from the smallest requirement

Before creating a context, describe precisely what the expression needs to do. Some helpful questions:

1. Does the expression only read properties or does it need to write values?
2. Does it need to call methods? If so, which methods and on which object types?
3. Does it need `T(...)` to reference classes or `new` to create objects?
4. Does it need to access Spring beans?
5. Which variables and functions are genuinely necessary?
6. Does the root object contain data or behavior beyond what is needed?
7. Who has permission to create or modify expressions: the development team, administrators, or end users?

If the answer is simply "read a few attributes and compare", SimpleEvaluationContext in read-only mode is usually a suitable starting point. If a specific function is needed, you can provide that function in a dedicated context. If type references or constructors are needed, use StandardEvaluationContext while restricting resolvers and allowed types.

Do not choose a context solely based on whether the current expression runs. Also consider other expressions that could be evaluated in the same use case and the data they are permitted to see.

## 4. Read-only property use case

For example, a rule that determines whether an order meets a minimum threshold. The expression only needs to read total and minimumTotal from an input DTO.

    public class OrderRuleInput {
        private final BigDecimal total;
        private final BigDecimal minimumTotal;

        public OrderRuleInput(
                BigDecimal total, BigDecimal minimumTotal) {
            this.total = total;
            this.minimumTotal = minimumTotal;
        }

        public BigDecimal getTotal() {
            return total;
        }

        public BigDecimal getMinimumTotal() {
            return minimumTotal;
        }
    }

Evaluating with a read-only context:

    OrderRuleInput input =
            new OrderRuleInput(orderTotal, configuredMinimum);

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("total >= minimumTotal");

    Boolean accepted =
            expression.getValue(context, input, Boolean.class);

The root object is OrderRuleInput; total and minimumTotal are read from the two DTO properties. The context does not need permission to call services, access beans, or create objects.

If you need to pass variables named via setVariable(), choose a context with an appropriate variable API, such as a StandardEvaluationContext restricted as needed. For rules that only need a few values, a small input DTO also keeps the data contract clear and avoids depending on many scattered variables.

## 5. Use case needing restricted instance methods

Sometimes a rule needs to call a simple method on input data, such as checking a string or retrieving a normalized value. SimpleEvaluationContext can enable instance method access via its builder when needed.

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .withInstanceMethods()
                    .build();

Example expression:

    customerCode.startsWith('AB-')

Enabling instance methods adds the ability to invoke methods on objects supplied by property accessors. Therefore, use this option only when it is part of the use case contract. Do not place services, repositories, or behavior-heavy objects into the root just to invoke a convenient method.

If only a specific check is needed, a DTO with precomputed properties or a narrow application-provided function can make the access scope easier to control. Weigh the cost of opening method access against preparing data beforehand.

## 6. Use case needing application-approved functions

If a rule needs to call a preselected Java computation, you can register a public static method as a function. This is suitable when you want expressions to have a stable alias without allowing calls to every method on the root object.

Example:

    Method normalizeMethod =
            RuleFunctions.class.getMethod(
                    "normalizeCode", String.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setMethodResolvers(Collections.emptyList());
    context.setConstructorResolvers(Collections.emptyList());

    context.registerFunction(
            "normalizeCode", normalizeMethod);

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customerCode)");

    String code =
            expression.getValue(context, String.class);

A registered function is still Java code running with the application's privileges. Therefore, register only necessary methods, prefer pure functions with clear inputs/outputs, and avoid I/O or mutating business state.

In the example, the default method resolvers and constructor resolvers are removed so expressions cannot invoke instance methods or create arbitrary objects via those resolvers. The function is registered directly in the context. If the expression also needs type references, review and configure TypeLocator separately; do not enable every capability by default just because functions require StandardEvaluationContext.

Do not register an entire utility class or many spare functions just for the convenience of rules that might appear in the future. Provide the exact set of functions that each rule group needs.

## 7. Use case needing type references or constructors

Some expressions need `T(...)` to reference types, call static members, or use `new` to create objects. SimpleEvaluationContext does not support these features by default. When genuinely required, StandardEvaluationContext can be used.

Type reference example:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    Expression expression =
            parser.parseExpression(
                    "T(java.time.LocalDate).of(2026, 11, 12)");

    LocalDate date =
            expression.getValue(context, LocalDate.class);

However, the default StandardTypeLocator can resolve many classes on the classpath. If expressions come from a source that is not fully trusted, restrict TypeLocator using an allowed list of types instead of permitting arbitrary class references.

Similarly, StandardEvaluationContext's default constructor resolver can allow instantiating resolved types. If the use case does not need `new`, remove the constructor resolver or replace it with one that only permits selected constructors.

Do not use `registerImport()` as a security allowlist. Registering package prefixes helps shorten class names; it is not a strict mechanism for restricting which types an expression can reference.

## 8. Restricting method and constructor resolvers

StandardEvaluationContext allows replacing its resolver lists. If a use case does not need method calls, you can remove the default method resolver:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setMethodResolvers(Collections.emptyList());

Similarly, if the expression does not need to instantiate objects:

    context.setConstructorResolvers(Collections.emptyList());

These snippets illustrate disabling the corresponding capability entirely. If a few selected operations are needed, provide a custom resolver with a specific method or constructor allowlist. Merely clearing the default resolver causes any method call or constructor call without a matching resolver to be rejected.

Keep in mind that method invocation and property access are two distinct capabilities. Reading JavaBean properties usually goes through getters via PropertyAccessor; removing MethodResolver does not automatically make all getters unreadable. If read-only access is needed, use a read-only context or an appropriate read-only PropertyAccessor.

## 9. Restricting property access and the object graph

The root object is a major part of the access surface. Placing a large JPA entity or a service object into the context exposes more properties and getters to the expression than necessary.

Prefer:

- DTOs or projection objects containing only the data serving the rule.
- Read-only property accessors when the rule does not need to update data.
- Shallow object graphs with controlled size and relationships.
- Avoiding getters with side effects, unwanted lazy queries, or high cost.
- Not placing passwords, tokens, payment details, or secrets into the root if the rule does not need them.

If a custom property accessor is needed, register the exact accessor for the specific data type. Do not add a generic accessor that can read every field or invoke every getter on every object in the application.

Reading a property is not always a pure operation. A getter can execute Java code, load data, or throw exceptions. Inspect the behavior of input objects rather than only the property names in the expression.

## 10. BeanResolver and Spring bean access permissions

SpEL expressions can reference beans using the `@beanName` syntax when EvaluationContext is configured with a BeanResolver. This capability is convenient for certain application-managed configurations, but it can open a path to services or components with broad privileges.

Do not configure a BeanResolver for every context just because one rule needs to access a bean. If an expression only needs the result of a calculation, compute it beforehand in Java and pass the result via a variable or root DTO. If beans are genuinely needed, allow only trusted expressions and consider a BeanResolver restricted to an allowed list of beans.

StandardEvaluationContext does not automatically have access to all beans in ApplicationContext unless a BeanResolver is configured. However, once the application attaches BeanFactoryResolver or a similar resolver, the scope of beans an expression can reference must be explicitly managed.

Services invoked from an expression can perform I/O, write data, or trigger external actions. Do not treat an expression as a harmless calculation if it has permission to call such beans.

## 11. Creating dedicated contexts per use case group

Context construction can be encapsulated into purpose-named factory methods. For example:

    public final class RuleContexts {

        private RuleContexts() {
        }

        public static EvaluationContext forReadOnlyOrder() {
            return SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();
        }

        public static StandardEvaluationContext
                forTrustedTypeRules(Object root) {
            StandardEvaluationContext context =
                    new StandardEvaluationContext(root);

            // Register only the TypeLocator and resolvers
            // approved for this rule group.

            return context;
        }
    }

Factory names clarify the privilege level and purpose of the context. Do not create a generic factory named `createDefaultContext()` and gradually add every capability requested by different groups.

In a large system, contexts can be separated by group:

| Use case | Starting context | Capabilities to consider |
|---|---|---|
| Property reading and comparison | Read-only SimpleEvaluationContext | Root DTO, necessary properties |
| Property reading and restricted instance method calls | SimpleEvaluationContext with instance methods | DTO with safe methods |
| Calling selected Java functions | Configured StandardEvaluationContext | Narrow function list |
| Type references or constructors | Configured StandardEvaluationContext | TypeLocator and resolver allowlists |
| Rules with bean references | Dedicated context for trusted rules | Restricted BeanResolver |

This table is a starting point for design. Actual capabilities must be determined by the Spring version, data types, and expressions that the application supports.

## 12. Do not share mutable contexts across requests

EvaluationContext holds mutable data such as the root object, variables, and resolver lists. If a context is shared across multiple requests and each request mutates the root or variables, data across evaluations can leak into one another.

Risky example:

    sharedContext.setRootObject(orderForCurrentRequest);
    sharedContext.setVariable("tenantId", currentTenantId);

If two requests run concurrently, one request may mutate the context while the other is evaluating an expression. This can cause rules to read the wrong data or produce hard-to-reproduce bugs.

A safer pattern is to parse a stable Expression once, then create a dedicated context for each evaluation:

    Expression expression =
            parser.parseExpression("total >= #minimumTotal");

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setMethodResolvers(Collections.emptyList());
    context.setConstructorResolvers(Collections.emptyList());
    context.setVariable("minimumTotal", configuredMinimum);

    Boolean result =
            expression.getValue(context, Boolean.class);

If a context is intentionally shared, ensure its configuration is immutable after initialization and do not update root/variables/resolvers concurrently. Do not rely on an assumption that a mutable context is inherently thread-safe.

## 13. Separating contexts by expression trust level

The origin of an expression is a key factor in deciding appropriate privilege levels.

- Rules written in application code and reviewed may require a set of predefined capabilities.
- Rules configured by administrators need validation, auditing, and capability restrictions by role.
- Expressions entered by end users require a very narrow scope; in many cases they should be replaced by a structured DSL or filter instead of accepting arbitrary SpEL.

Do not use the same context for both internal rules and user expressions just because they share syntax. An untrusted expression should not be granted permission to call methods, create objects, or access beans merely because an internal use case needs those permissions.

Separating contexts along trust boundaries helps control change. When one rule group needs an additional capability, that capability can be evaluated independently without automatically expanding privileges for all other groups.

## 14. Testing the context as part of the rule contract

Tests should not only verify that an expression returns the expected result. They must verify that the context allows the exact necessary operations and rejects out-of-scope operations.

A suitable test suite may include:

- Valid property-reading expressions succeed.
- Properties that are not provided or not permitted to be accessed are rejected.
- Method calls run only when the use case enables the corresponding capability.
- Constructor references are rejected in contexts that disallow object creation.
- Type references resolve only types in the allowlist if restrictions are configured.
- Bean references do not work when the context has no BeanResolver.
- Missing, null, or wrong-type variables are handled according to the contract.
- The root object does not contain data or behavior beyond what is needed.
- Contexts from two requests do not leak each other's root object or variables.

When testing rejection behavior, verify that errors are handled cleanly and do not expose internal data. An expression being rejected is the expected outcome if it exceeds the context's capabilities.

## 15. Common mistakes

| Practice | Problem | How to address |
|---|---|---|
| Using StandardEvaluationContext for every rule | Every use case inherits a broad capability set | Choose a context according to minimum needs |
| Passing entities or services as the root object | Expressions see an overly broad object graph and behavior | Use read-only DTOs |
| Registering spare functions preemptively | Increases the number of methods rules can call | Register only necessary functions |
| Enabling BeanResolver for all contexts | Rules can reference beans beyond what is needed | Do not configure it or use an allowlisted resolver |
| Treating registerImport() as an allowlist | Package prefixes only assist short-name resolution | Use TypeLocator to control specific types |
| Sharing mutable contexts across requests | Root and variables can overwrite each other | Create a dedicated context per evaluation |
| Testing only valid outcomes | Fails to detect unintended capabilities | Test both permitted and rejected operations |

## Conclusion

EvaluationContext should accurately reflect the expression's use case. For data-reading rules, start with SimpleEvaluationContext in read-only mode. When instance methods, functions, type references, constructors, or bean references are needed, enable only the corresponding capability and restrict accessible objects, resolvers, or types.

Use small DTOs instead of high-privilege entities or service objects, register the exact required variables and functions, create a dedicated context for each evaluation with mutable data, and test both allowed and rejected behaviors. StandardEvaluationContext is a flexible tool for cases requiring advanced features; it should not become the default context for every rule simply because it offers many capabilities.