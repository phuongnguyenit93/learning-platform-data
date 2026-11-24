# Do Not Expose the Entire ApplicationContext to SpEL Expressions

Spring Expression Language (SpEL) can access objects and invoke methods provided through an EvaluationContext. If you pass the entire `ApplicationContext` or `BeanFactory` as the root object or as a variable, an expression can use container APIs to look up additional beans and dependencies. The access scope then becomes far broader than the data or operations a single use case needs.

Secure design should grant an expression only the exact capabilities it requires: input data via the root object or variables, and narrow-API facades if calling application logic is necessary. Do not turn ApplicationContext into a service locator that expressions can freely explore.

## 1. Why Is ApplicationContext Overly Privileged?

ApplicationContext is Spring's central bean management container. Beyond retrieving beans by name or type, it provides capabilities related to BeanFactory, resource loading, event publishing, the environment, and container lifecycle.

If an expression can directly access the context, it can attempt to call APIs such as:

    #applicationContext.getBean('paymentService')
    #applicationContext.getBeanFactory()
    #applicationContext.publishEvent(#event)

Specific method names and invocation availability still depend on the object, resolvers, and EvaluationContext configuration. However, when ApplicationContext is exposed, expressions can discover far more components than intended instead of using only a restricted API.

Risks can include:

- Accessing repositories or services outside the scope of the current use case.
- Calling methods that can write data, send messages, process payments, or mutate state.
- Reading configurations or beans containing sensitive information.
- Resolving beans by name or type chosen arbitrarily by the expression author.
- Triggering unintended bean initialization when calling `getBean`.
- Creating hidden dependencies, making permission checks, initialization order, and side effects hard to verify.

Do not treat ApplicationContext as an ordinary data object. It is the gateway to the container and the capabilities the container manages.

## 2. Do Not Set ApplicationContext as the Root Object or a Variable

Avoid creating the context like this:

    StandardEvaluationContext context =
            new StandardEvaluationContext(applicationContext);

Or:

    context.setVariable("applicationContext", applicationContext);

In both cases, the expression can access the ApplicationContext object through property/method access enabled in the EvaluationContext. For example:

    #applicationContext.getBean('orderRepository')

If the root object is ApplicationContext, the expression can start with properties or methods without a variable prefix, depending on how resolvers handle it. If the context is registered as a variable, the expression uses `#applicationContext`.

Instead, set the root object to a data model restricted to the use case:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setVariable("customer", customerView);

The root object and variables should be DTOs, view models, or domain objects with just enough API. Do not put the container, service locators, or administrative objects into the context simply so expressions can discover other dependencies.

## 3. Distinguishing Bean References from Exposing ApplicationContext

The `@beanName` syntax in SpEL uses the EvaluationContext's BeanResolver to resolve beans by name. This is a separate mechanism and does not require putting ApplicationContext as the root object.

Example connecting StandardEvaluationContext to the entire BeanFactory:

    context.setBeanResolver(
            new BeanFactoryResolver(applicationContext.getBeanFactory())
    );

This allows expressions to use `@pricingService`, but BeanFactoryResolver can resolve many beans managed by the BeanFactory. If the expression is not fully trusted, opening a global resolver can still be too broad.

Distinguish between:

- **Exposing ApplicationContext directly:** the expression receives the container object and can call container APIs.
- **BeanFactoryResolver:** the expression uses `@name` syntax to resolve beans through the resolver.
- **Custom BeanResolver:** the application controls the exact bean names that can be resolved.
- **Variable:** the application places a specific object into the context with `setVariable`.

If only a single capability is needed, provide that exact object instead of providing the container for the expression to search on its own.

## 4. Use Variables for Evaluation Data

When an expression needs input data, pass that data through variables:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setVariable("customer", customerView);
    context.setVariable("discountRate", new BigDecimal("0.05"));
    context.setVariable("region", "VN");

    ExpressionParser parser = new SpelExpressionParser();

    Object result = parser.parseExpression(
            "total * (1 - #discountRate)"
    ).getValue(context);

The expression only sees the root object and the variables provided by the application. It needs no bean-lookup privileges to read data.

Prefer immutable objects or read-only DTOs with the properties needed for the expression. Avoid passing entities managed by a persistence context if the expression does not need permission to modify entities or traverse deep relationships. Data passed in must undergo access control checks before creating the EvaluationContext.

## 5. Use Narrow-API Facades for Necessary Operations

If an expression needs to invoke a few methods, create a facade exposing only those exact operations. For example:

    public final class PricingExpressionFacade {

        private final PricingService pricingService;

        public PricingExpressionFacade(
                PricingService pricingService) {
            this.pricingService = pricingService;
        }

        public BigDecimal calculatePreview(OrderView order) {
            return pricingService.calculatePreview(order);
        }

        public String defaultCurrency() {
            return "VND";
        }
    }

This facade does not expose the entire PricingService and does not provide methods such as capture payment, refund, or delete order if the use case does not need them.

The facade can be passed as a variable:

    context.setVariable("pricing", pricingExpressionFacade);

    #pricing.calculatePreview(#root)

This keeps clear which object the expression is using. If you want to use bean reference syntax, resolve the facade using a BeanResolver restricted to specific bean names.

Prefer pure computational or read-only methods. If an expression needs to initiate a data-writing action, consider calling the business service from Java after checking permissions, rather than letting the expression arbitrarily invoke methods with side effects.

## 6. Restricting Bean Names with a Custom BeanResolver

When `@beanName` syntax is genuinely needed, you can implement a BeanResolver that returns only allowlisted facades:

    public final class AllowlistBeanResolver
            implements BeanResolver {

        private final Map<String, Object> allowedBeans;

        public AllowlistBeanResolver(
                Map<String, Object> allowedBeans) {
            this.allowedBeans = Map.copyOf(allowedBeans);
        }

        @Override
        public Object resolve(
                EvaluationContext context,
                String beanName) throws AccessException {

            Object bean = allowedBeans.get(beanName);
            if (bean == null) {
                throw new AccessException(
                        "Bean is not available: " + beanName
                );
            }
            return bean;
        }
    }

Configuring the context:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setBeanResolver(
            new AllowlistBeanResolver(
                    Map.of("pricing", pricingExpressionFacade)
            )
    );

    Object preview = parser.parseExpression(
            "@pricing.calculatePreview(#root)"
    ).getValue(context);

The expression can resolve `@pricing`, while other names like `@paymentService`, `@orderRepository`, or `@applicationContext` will be rejected unless added to the allowlist.

This is an illustrative application-built implementation; `BeanResolver` and `AccessException` are Spring Expression APIs. The allowlist must be built from trusted configuration. Do not let expressions or users declare additional allowed bean names.

## 7. Bean Allowlists Still Require Method and Property Restrictions

Restricting bean names alone is insufficient if the exposed facade has too many public methods. Once a bean is resolved, SpEL still uses the EvaluationContext's method resolution and property access mechanisms to work with that object.

Therefore, restrict all of the following:

- **Beans:** resolve only the required facades.
- **Methods:** expose only methods appropriate for the use case; avoid general-purpose services.
- **Properties:** expose only data needed for reading; do not grant write permissions if unneeded.
- **Root and variables:** provide only authorization-checked, clearly scoped objects.
- **Expression features:** avoid enabling type references, constructor invocation, or other capabilities if the use case does not need them.

Do not create facades with general-purpose APIs like `execute(String command)`, `getBean(String name)`, or `invoke(String method, Object... args)`. Those methods can recreate the broad access that the initial allowlist was meant to prevent.

## 8. Choosing the Right EvaluationContext

SimpleEvaluationContext is designed for restricted use cases like data binding. It does not support bean references, type references, or constructor invocation; instance method invocation is also disabled by default.

Example of a read-only context:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(orderView)
                    .build();

This is the right choice when an expression only needs to read properties from a model.

StandardEvaluationContext provides more capabilities, including BeanResolver when configured, method invocation, and type/constructor resolution according to registered resolvers. Use it only when the use case genuinely requires those capabilities and has an appropriate restriction policy.

Do not switch to StandardEvaluationContext just to make an expression work if the expression comes from a user or a not-fully-trusted configuration source. Determine the minimal required capabilities first, then choose the context.

## 9. Do Not Use ApplicationContext for Self-Discovery of Dependencies

An expression should not decide for itself which service to use by calling `getBean` with dynamic data:

    #applicationContext.getBean(#serviceName).execute(#input)

This creates a general-purpose service locator. Whoever supplies the expression or `serviceName` data can influence which object is called, making access rights hard to control and test.

Move service selection into Java:

    Object result = switch (operation) {
        case "preview" -> pricingExpressionFacade.preview(input);
        case "validate" -> orderExpressionFacade.validate(input);
        default -> throw new IllegalArgumentException(
                "Unsupported operation"
        );
    };

The example above illustrates a dispatch allowlist. In a real application, operation selection must be validated against principal, tenant, and use case. The expression should only receive the corresponding result or facade after Java has decided which capability is allowed.

## 10. Isolating Contexts by Request, Tenant, and Purpose

Do not reuse an EvaluationContext whose root, variables, or resolvers hold state from a previous request for the next request. When an application serves multiple users or tenants, improper context reuse can leak data or capabilities across scopes.

Create a context per evaluation or per use case with a clear lifecycle:

    EvaluationContext createContext(
            OrderView order,
            CustomerView customer,
            PricingExpressionFacade pricing) {

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable("customer", customer);
        context.setVariable("pricing", pricing);

        return context;
    }

This is an illustrative structure. Before creating the context, the application layer must verify that the caller is permitted to view the corresponding order and customer. If a facade holds per-request or per-tenant state, do not store a shared instance in a global allowlist.

Keeping contexts separate also makes testing easier: tests can supply a mock facade and only the necessary variables without starting the entire ApplicationContext.

## 11. Bean Scope, Proxies, and Side Effects

If you need to use Spring-managed beans, retrieve the facade from the container at the configuration layer and preserve the Spring-created proxy. Do not unwrap the proxy to get the target object, because calls may need to pass through transaction, security, caching, or other advice.

Pay attention to bean scope. Request/session-scoped beans are only valid within their corresponding scope; prototype beans can create a new instance on every resolution. Do not hold a short-scoped object inside a long-lived shared resolver.

Also avoid calling methods with side effects in expressions meant only for display or calculation. Expressions may be evaluated multiple times. If a method sends notifications, writes to the database, or calls APIs, repeated evaluations can cause duplicate actions. Place actions in business services with explicit transactions, authorization, and idempotency.

## 12. Testing Capability Boundaries

There should be tests proving an expression can only access granted objects:

1. The expression can read required properties on the root object.
2. The expression can use registered variables.
3. Allowlisted facades can be resolved and permitted methods invoked.
4. Bean names outside the allowlist are rejected.
5. ApplicationContext or BeanFactory does not appear in the root/variables of contexts intended for untrusted expressions.
6. Out-of-scope methods are not exposed via facades.
7. One tenant's or request's context does not contain another tenant's or request's data.
8. Methods with side effects are not called outside expected counts and timing.

Example test for a rejected bean:

    assertThrows(
            AccessException.class,
            () -> resolver.resolve(context, "paymentService")
    );

In addition to unit tests for resolvers and facades, test expressions through the exact EvaluationContext used by the application. This helps catch configurations that inadvertently register additional accessors, resolvers, or overly broad objects.

## 13. Summary

Do not put the entire ApplicationContext or BeanFactory as the root object or a variable for an expression. Those objects enable dependency discovery and can open paths to many out-of-scope services, data, and operations. Pass data using restricted root objects/variables; use narrow-API facades for required capabilities; if `@beanName` is needed, use an allowlisted BeanResolver instead of resolving the entire BeanFactory. Restrict methods, properties, and side effects as well, choose SimpleEvaluationContext when only data binding is needed, and isolate EvaluationContext per request or tenant. Expressions should receive only exactly what the use case requires.
