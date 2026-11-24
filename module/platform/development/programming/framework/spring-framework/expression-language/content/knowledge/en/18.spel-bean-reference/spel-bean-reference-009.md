# Risks When Expressions Can Call Arbitrary Beans

Spring Expression Language (SpEL) supports referencing Spring beans using the **@beanName** syntax when EvaluationContext is configured with a BeanResolver. This capability is very convenient for expressions controlled by the application or development team: an expression can call service methods, read data from a bean, or combine pre-provided rules.

Risks arise when untrusted users are permitted to write expressions in a context capable of broad bean resolution. An expression can access highly privileged beans, invoke state-mutating methods, read sensitive data, or trigger resource-intensive operations. Successful parsing does not prove the expression is authorized to perform those actions.

Key principle: **do not grant a BeanResolver with access to the entire BeanFactory to user-controlled expressions**. Restrict beans, methods, data, and evaluation scope strictly to what is needed.

## 1. How do bean references in SpEL work?

### 1.1. The @beanName syntax

SpEL uses the **@** symbol to reference a bean by name:

~~~java
@pricingService.calculate(order)
~~~

The expression above asks EvaluationContext to resolve the bean named pricingService, then call the calculate method with the order argument.

Bean references can be combined with properties or methods in expressions:

~~~java
@featurePolicy.enabled('checkout')
@exchangeRateService.rate('USD', 'VND')
@catalogRepository.findByCode('P-100')
~~~

These expressions only work if the context has an appropriate BeanResolver. Writing the @beanName syntax does not automatically locate beans in every ExpressionParser or EvaluationContext.

### 1.2. BeanResolver

The extension point responsible for resolving beans is the BeanResolver interface in the org.springframework.expression package:

~~~java
public interface BeanResolver {
    Object resolve(
            EvaluationContext context,
            String beanName
    ) throws AccessException;
}
~~~

When the parser evaluates a bean reference, it asks BeanResolver to locate the corresponding object. The resolver returns the bean or throws AccessException if it cannot be resolved.

An EvaluationContext without a BeanResolver will not be able to resolve bean references. This is a useful restriction when an expression does not need bean access.

### 1.3. BeanFactoryResolver

Spring provides BeanFactoryResolver to connect SpEL with a Spring BeanFactory:

~~~java
BeanFactoryResolver resolver =
        new BeanFactoryResolver(beanFactory);

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setBeanResolver(resolver);
~~~

Once configured, expressions can use the syntax:

~~~java
@pricingService.calculate(order)
~~~

BeanFactoryResolver delegates bean lookup to the BeanFactory. If the BeanFactory contains many beans, this resolver can make those beans reachable by name for the expression to reference, depending on permissions and other capabilities granted in the context.

This is appropriate for trusted expressions managed by the application. For user-submitted expressions, granting a resolver pointing directly to the BeanFactory is usually overly broad.

### 1.4. Bean references differ from dependency injection

The @beanName syntax in SpEL is a request to resolve a bean at expression evaluation time. It is not the @Autowired annotation and does not automatically inject dependencies into a class.

Example:

~~~java
@pricingService.calculate(order)
~~~

The expression asks the resolver to retrieve the pricingService bean and call a method. Meanwhile, dependency injection typically occurs when Spring creates and configures the application's beans.

The two mechanisms serve different purposes. A bean reference in SpEL is a runtime capability that the context may or may not grant.

### 1.5. Special bean names and FactoryBean

Bean names can contain special characters. SpEL supports enclosing bean names in quotes after the @ symbol when needed:

~~~java
@'pricing-service'.calculate(order)
~~~

Spring also supports the **&** syntax to retrieve the FactoryBean itself instead of the object created by the FactoryBean:

~~~java
@&reportFactory
~~~

The ability to access a FactoryBean should be treated as a separate privilege. Do not allow users to reference a FactoryBean just because they need to use a regular bean; calling methods on the factory may open up additional object creation or unintended operations.

## 2. Where are bean references configured?

### 2.1. Configuration on StandardEvaluationContext

An application can manually create a context and explicitly attach a BeanResolver:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);

Object result = parser
        .parseExpression("@pricingService.calculate(#root)")
        .getValue(context);
~~~

The example assumes applicationContext has a pricingService bean. When the context is given this resolver, the expression can reference beans by name.

Not every StandardEvaluationContext automatically has a BeanFactoryResolver. If the application does not call setBeanResolver and no other mechanism supplies a resolver, bean references will not be resolved.

### 2.2. Bean expressions in Spring configuration

Spring uses SpEL in several configuration locations such as @Value annotation values and expressions in bean definitions. StandardBeanExpressionResolver is a container component used to evaluate bean expressions within the Spring context.

Example:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

A bean expression in Spring configuration can be evaluated by the container using the context and bean resolution capabilities provided by the container.

These are application configuration expressions. Configuration sources are typically controlled by deployment and review processes. You should not extrapolate that every expression received from an API, form, or database needs the same privileges as internal configuration expressions.

### 2.3. Only grant a resolver when genuinely needed

If an expression only reads properties on a DTO or performs comparisons, there is no need to attach a BeanResolver. Omitting the resolver from the context eliminates the ability to use bean reference syntax.

Example context without a bean resolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

Boolean allowed = parser
        .parseExpression("active && score >= 80")
        .getValue(context, Boolean.class);
~~~

This configuration is better suited when an expression only needs pre-prepared data. However, also restrict method resolvers, property accessors, type locators, and constructor resolvers if the expression is untrusted.

## 3. Why are arbitrary bean references dangerous?

### 3.1. Accessing highly privileged beans

A Spring application can contain many beans serving sensitive tasks:

- Repositories or services accessing customer data.
- DataSources or database access components.
- Components sending emails, notifications, or messages.
- Services manipulating files or storage.
- Services managing accounts, permissions, and login sessions.
- Components integrating with external systems.
- Factories or registries capable of creating and locating other objects.

If an expression can arbitrarily reference these beans, the expression author can invoke methods that the application intended only for trusted processing flows.

The risk is not limited to reading beans. Methods can write data, send messages, change state, or execute transactions.

### 3.2. Calling methods with side effects

For example, a context might resolve a mailSender bean. If an expression is permitted to call email-sending methods, a user could trigger sending notifications outside the intended business workflow.

Similarly, methods on a repository can query data or mutate state if the API provides write operations. Methods on a storage service can read or write files.

Even when an expression is only used to evaluate a condition, calling methods in predicates or ternary branches can still trigger side effects. Do not treat a Boolean expression as read-only if the methods it calls can mutate state.

### 3.3. Data leakage

A bean can return objects containing sensitive information. If an expression can read properties or call methods on those objects, data can leak into results, logs, error messages, or API responses.

A multi-level access chain can navigate from an allowed bean to other objects:

~~~java
@customerService.findById(#customerId).account.owner.email
~~~

Allowing an initial bean does not mean every object returned by that bean is safe to expose to expressions. Access can propagate along the object graph and the methods those objects provide.

### 3.4. Probing bean names and application structure

When a resolver lets expressions try multiple bean names, an expression author can probe which names exist through differences between successful resolution and errors.

Detailed error messages can inadvertently disclose class names, bean names, packages, or internal structure. Do not return raw stack traces or Spring exception messages to untrusted clients.

Use an explicit list of allowed beans, return generic error messages at the API layer, and store technical details in controlled internal logs.

### 3.5. Resource consumption

A referenced bean may execute large queries, call network services, process large collections, or allocate memory-heavy objects. Even a short expression can trigger an expensive method.

If users can submit many expressions or repeat resource-intensive calls, the system can become overloaded. Therefore, controlling bean references must go hand in hand with limits on evaluation count, input data, and method cost.

## 4. Do not grant the entire BeanFactory to untrusted expressions

### 4.1. Risks of a general-purpose resolver

The following configuration is convenient for internal expressions:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);
~~~

However, this resolver delegates lookups to the BeanFactory. If expressions are user-controlled, granting broad resolution privileges significantly increases the attack surface.

Do not enforce an allowlist only in the UI while still passing BeanFactoryResolver to the context. Enforcement must live at the resolver or execution boundary that users cannot bypass.

### 4.2. Do not attach a resolver when unnecessary

This is the simplest and easiest-to-verify option:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

// Do not call setBeanResolver if the expression does not need a bean reference.
~~~

An expression cannot use @beanName if the context has no resolver. When a value from a service is needed, compute that value in Java and pass the validated result into the context as a variable or DTO property.

### 4.3. Grant minimal beans

If an expression genuinely needs to invoke a few services, create a narrow facade with methods serving only that purpose. Do not directly grant broadly privileged beans such as the application context, generic repositories, or administrative services.

Facade example:

~~~java
public class PricingExpressionFacade {

    private final PricingService pricingService;

    public PricingExpressionFacade(PricingService pricingService) {
        this.pricingService = pricingService;
    }

    public BigDecimal quote(String productCode) {
        return pricingService.quote(productCode);
    }
}
~~~

The facade only provides the quote method under the chosen contract. It does not expose administrative operations, arbitrary data writes, or access to other services.

However, a facade does not automatically make an expression safe. The quote method still needs to validate arguments, limit queries, and ensure it does not expose another tenant's data.

## 5. Using an allowlist-based BeanResolver

### 5.1. Concept

If bean references must be supported, you can implement a BeanResolver that allows only a specific set of bean names. The resolver rejects all other names before accessing the BeanFactory.

Example:

~~~java
public final class AllowListBeanResolver implements BeanResolver {

    private final BeanFactoryResolver delegate;
    private final Set<String> allowedBeanNames;

    public AllowListBeanResolver(
            BeanFactory beanFactory,
            Set<String> allowedBeanNames) {

        this.delegate = new BeanFactoryResolver(beanFactory);
        this.allowedBeanNames = Set.copyOf(allowedBeanNames);
    }

    @Override
    public Object resolve(
            EvaluationContext context,
            String beanName) throws AccessException {

        if (!allowedBeanNames.contains(beanName)) {
            throw new AccessException(
                    "Bean reference is not allowed"
            );
        }

        return delegate.resolve(context, beanName);
    }
}
~~~

Registering the resolver:

~~~java
BeanResolver resolver = new AllowListBeanResolver(
        beanFactory,
        Set.of("pricingExpressionFacade")
);

StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

context.setBeanResolver(resolver);
~~~

At this point, the expression can only resolve the name pricingExpressionFacade through this resolver.

Valid example:

~~~java
@pricingExpressionFacade.quote('P-100')
~~~

Rejected example:

~~~java
@dataSource.getConnection()
~~~

### 5.2. Controlling aliases and FactoryBean dereferencing

When using an allowlist, decide explicitly:

- Whether bean aliases are allowed.
- Whether the **&** prefix to access a FactoryBean is allowed.
- Whether multiple different names pointing to the same bean are allowed.
- Whether bean names with special characters are allowed.
- Whether permissions need to be scoped by tenant or user group.

A name-based allowlist must match the exact naming convention received by the resolver. Do not accidentally widen it with wildcards or allow all names sharing a prefix in case new beans are added later.

The example above only checks exact names and forwards them to BeanFactoryResolver. If the application does not need FactoryBean dereferencing, reject names starting with the **&** symbol and test with real expressions in the Spring version in use.

### 5.3. A bean allowlist is not enough to restrict methods

Even when only one bean is allowed, the expression can still call public methods on that bean and access objects returned by those methods.

Example:

~~~java
@pricingExpressionFacade.quote('P-100').getClass()
~~~

This is why the facade must have a small API, return simple data types, and avoid exposing internal objects. You must also restrict other capabilities in the context, such as type references, constructors, property accessors, and method resolvers.

A bean name allowlist is a useful control layer, not a complete sandbox.

## 6. Restricting method invocation and property access capabilities

### 6.1. Do not pass a service directly when only data is needed

If an expression only needs to know a customer's status, query it in Java and pass a Boolean value into the context:

~~~java
boolean customerActive =
        customerService.isActive(customerId);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerActive", customerActive);
~~~

The expression only needs:

~~~java
#customerActive
~~~

This approach removes the need for bean references and reduces the number of methods callable from the expression.

### 6.2. Consider SimpleEvaluationContext

SimpleEvaluationContext is designed for a subset of SpEL with more restricted privileges than StandardEvaluationContext. It does not provide full capabilities such as type references, constructors, and bean references.

Read-only context example:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

If method invocation is needed, only enable the resolvers or features genuinely required using the builder API of the Spring version in use. Do not add a general bean resolver to solve a small requirement.

SimpleEvaluationContext helps restrict expression capabilities, but does not automatically limit input size, evaluation count, external method execution time, or getter cost. Those limits remain the application's responsibility.

### 6.3. Controlling the object graph

The root object, allowed beans, and method results can lead to many other objects. Keep the object graph small:

- Use DTOs or expression views instead of entities with many relationships.
- Do not expose ApplicationContext, BeanFactory, or a service locator.
- Do not return objects with administrative privileges from a facade.
- Avoid getters with side effects or that perform queries.
- Avoid returning unbounded large collections.
- Provide only the properties that the predicate truly needs.

Controlling the root object and return values prevents expressions from traversing from a small entry point into the entire application structure.

## 7. Authorization and tenant isolation

A bean may be shared across multiple users or tenants. If an expression can call a bean without passing full authorization context, it could access data outside the current user's scope.

For example, a repository method taking customerId does not imply the user is permitted to query any customerId. Authorization must be checked in the service or repository according to the actual principal and tenant.

Several principles:

- Do not rely on expressions as the sole means of performing authorization.
- Check permissions in the service before returning data or performing operations.
- Do not let users choose administrative beans or tenant resolvers themselves.
- Do not reuse a single shared EvaluationContext across requests with different variable data.
- Create contexts scoped to the request or evaluation.
- Do not place tokens, credentials, or secrets into variables readable by expressions.

If the same expression is evaluated for multiple tenants, ensure the called bean receives the correct tenant context from a trusted source. Do not treat a tenantId self-declared by the expression as the sole basis for authorization.

## 8. Controlling expression size and evaluation frequency

Bean references can trigger resource-intensive methods. Therefore, limit both the expression and how it is used:

- Limit string length before parsing.
- Limit evaluation count per user, tenant, or time window.
- Limit argument count and collection sizes.
- Set appropriate timeouts for I/O operations inside services.
- Do not expose methods with unbounded queries.
- Avoid calling services from predicates evaluated over every element of a large collection.
- Cache results only when semantics and permission boundaries permit.
- Monitor parse time, evaluation time, and bean call counts.

Timeouts at the result-waiting layer do not guarantee stopping a running Java method. Methods need their own time bounds and controlled termination capability. For high-risk untrusted workloads, consider isolation in a separate process or environment with resource limits.

## 9. Handling bean reference errors

Errors related to bean references commonly appear during evaluation:

| Symptom | Possible cause | Resolution direction |
|---|---|---|
| Bean reference not supported | Context has no BeanResolver | Do not use @beanName or configure a controlled resolver |
| Bean not found | Wrong name, alias, or bean does not exist | Check bean configuration on the application side |
| Bean rejected | Allowlist does not permit that name | Confirm requirement and update allowlist via review |
| Cannot call method | Method does not exist, is not public, or arguments mismatch | Check facade API and argument types |
| Method throws exception | Logic inside the bean failed | Handle the root cause in the service and preserve cause |
| Property inaccessible | Accessor does not support it or property does not exist | Check DTO and property accessors |
| Result leaks out-of-scope data | Bean or method returns an overly broad object | Narrow the API and verify authorization |
| Evaluation too slow | Method performs I/O or processes large data | Limit methods, data, and frequency |

Do not catch all bean reference errors and return null or a default value. Doing so can hide misspelled bean names, denied permissions, or failing services.

Distinguish configuration errors, permission errors, and business errors. In public APIs, return safe messages; in internal logs, record error codes and technical causes according to security policy.

## 10. Safer configuration example

Suppose a rule only needs to call a facade to look up a product's price. Instead of granting the entire ApplicationContext, create a facade and a bean name allowlist:

~~~java
PricingExpressionFacade facade =
        new PricingExpressionFacade(pricingService);

BeanFactory beanFactory = applicationContext;

StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

context.setBeanResolver(
        new AllowListBeanResolver(
                beanFactory,
                Set.of("pricingExpressionFacade")
        )
);
~~~

Expression:

~~~java
@pricingExpressionFacade.quote('P-100') > #minimumPrice
~~~

Points to ensure:

1. The facade provides only the necessary quote method.
2. The method validates the product code and checks data access permissions.
3. The return type is a simple type, not a service or administrative object.
4. The minimumPrice variable is constructed from validated data.
5. The context is created per usage scope, without sharing state across requests.
6. The expression source is controlled by policy, length, and frequency.
7. Other capabilities such as type references and constructors are also restricted if the expression is untrusted.

If only comparing against minimumPrice is needed, a simpler approach is to call the facade in Java, retrieve the value, and pass it into the context. Then the expression needs no bean reference:

~~~java
BigDecimal price = facade.quote(productCode);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("price", price);
context.setVariable("minimumPrice", minimumPrice);
~~~

~~~java
#price > #minimumPrice
~~~

This approach is usually easier to control because the service is called at an explicit Java location, while SpEL only processes pre-prepared data.

## 11. Checklist before allowing bean references

Before enabling BeanResolver for a group of expressions, confirm:

- The expression source is trusted or controlled by policy.
- There is a concrete reason requiring bean references; otherwise, do not configure a resolver.
- A general-purpose BeanFactoryResolver is not granted to untrusted expressions.
- The resolver permits only specific bean names and does not use broad wildcards.
- Aliases and FactoryBean dereferencing are handled explicitly.
- Allowed beans have a small API, and methods with side effects are controlled.
- Methods do not return ApplicationContext, service locators, or sensitive objects.
- The root object and object graph contain only necessary data.
- Authorization is enforced in services, not relied upon in expressions.
- Tenant context comes from a trusted source.
- Expression length, data, call count, and evaluation cost are bounded.
- Parse errors, access errors, and service errors are handled separately.
- Stack traces or internal bean names are not returned to clients.
- Tests cover allowed beans, rejected beans, and failing methods.

## 12. Summary

Bean references let SpEL access Spring beans via the **@beanName** syntax through BeanResolver. BeanFactoryResolver is a convenient choice when trusted expressions need to resolve beans from BeanFactory, but it can open broad access if granted to user-controlled expressions.

To reduce risk:

- Do not configure a BeanResolver when an expression does not need beans.
- Avoid granting the entire BeanFactory to untrusted expressions.
- If needed, use an allowlist-based BeanResolver and expose only a facade with a narrow API.
- Restrict method invocation, property access, and the object graph.
- Perform authorization and tenant isolation in services.
- Limit size, frequency, and execution cost.
- Do not treat a bean allowlist or SimpleEvaluationContext as a complete resource sandbox.

SpEL should receive only the minimal data and capabilities needed to express rules. When an expression needs to access a highly privileged service or perform an important business action, consider performing the action in Java and placing only the required result into EvaluationContext.