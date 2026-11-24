# Do Not Expose Beans Beyond the Scope Needed by an Expression in SpEL

Spring Expression Language (SpEL) can reference beans using the `@beanName` syntax when EvaluationContext is configured with a BeanResolver. This approach is convenient because expressions can call methods or read properties of Spring-managed components. However, exposing the entire BeanFactory to the expression's scope lets an expression reach more services and resources than the use case requires.

The principle to apply is **least privilege**: expose only the beans genuinely needed for the expression, with a narrow API and appropriate permissions. The fact that a bean exists in the Spring container does not mean every expression needs permission to reference that bean.

## 1. Risks of exposing too many beans

When StandardEvaluationContext uses BeanFactoryResolver pointing to the application's BeanFactory, expressions can resolve many beans by name:

    @pricingService
    @orderRepository
    @paymentService
    @notificationService

If these beans are exposed, expressions can call public methods on the resolved objects. Depending on application design, those methods may:

- Read sensitive data or data outside the current user's scope.
- Write, modify, or delete data in the database.
- Send emails, publish messages, or call external services.
- Perform payment operations, change permissions, or update state.
- Instantiate additional objects or access shared resources.

The risk does not lie solely in bean names. An exposed bean may contain many public methods, and the default ReflectiveMethodResolver can resolve matching method calls on that object. Therefore, allowing references to a broadly privileged bean can indirectly open up many operations unrelated to the expression's purpose.

Do not place ApplicationContext, BeanFactory, or a general-purpose administrative service into the expression context just so the expression can look up additional dependencies on its own. That blurs the clear boundary between capabilities the application intentionally grants and capabilities the expression can discover by itself.

## 2. Only use BeanResolver when the expression genuinely needs beans

Bean references are resolved through EvaluationContext's BeanResolver. With StandardEvaluationContext, the entire BeanFactory can be connected using BeanFactoryResolver:

    context.setBeanResolver(
            new BeanFactoryResolver(applicationContext.getBeanFactory())
    );

This configuration is convenient for trusted internal expressions, but the resolution scope spans all beans and aliases provided by the factory. If expressions come from users, tenants, editable configuration, or not fully trusted sources, granting such a broad resolver can exceed what is needed.

If an expression only needs to read a precomputed value, pass that value via a variable or root object instead of exposing an entire service. If an expression needs a few computational operations, provide a small facade containing only the necessary methods.

## 3. Creating an allowlist-based BeanResolver

A custom BeanResolver can be implemented to resolve only a set of bean names permitted by the application. Example:

    public final class AllowlistBeanResolver implements BeanResolver {

        private final Map<String, Object> allowedBeans;

        public AllowlistBeanResolver(Map<String, Object> allowedBeans) {
            this.allowedBeans = Map.copyOf(allowedBeans);
        }

        @Override
        public Object resolve(
                EvaluationContext context, String beanName)
                throws AccessException {

            Object bean = allowedBeans.get(beanName);
            if (bean == null) {
                throw new AccessException(
                        "Bean is not available to this expression: " + beanName
                );
            }

            return bean;
        }
    }

When creating the context, pass only the allowed objects:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setBeanResolver(
            new AllowlistBeanResolver(
                    Map.of("pricing", pricingExpressionFacade)
            )
    );

    ExpressionParser parser = new SpelExpressionParser();

    Object result = parser.parseExpression(
            "@pricing.calculatePreview(#order)"
    ).getValue(context);

In this example, the expression can only resolve the bean reference named `pricing`. Names such as `@paymentService` or `@orderRepository` that are not in the allowlist will be rejected.

`AllowlistBeanResolver` is illustrative application-implemented code; `BeanResolver` is a Spring interface in the `org.springframework.expression` package. In a real implementation, also check empty bean names, aliases, naming conventions, and error reporting according to application policy. Do not obtain the allowlist map from data submitted by untrusted expressions or users.

## 4. Exposing a facade with a narrow API

A bean name allowlist only restricts which objects can be resolved. It does not restrict which methods on those objects can be called. If a large service is placed directly into the allowlist, expressions can still see many public methods of that service.

A dedicated facade for SpEL should have a small and clear API:

    public final class PricingExpressionFacade {

        private final PricingService pricingService;

        public PricingExpressionFacade(PricingService pricingService) {
            this.pricingService = pricingService;
        }

        public BigDecimal calculatePreview(OrderView order) {
            return pricingService.calculatePreview(order);
        }

        public String getDefaultCurrency() {
            return "VND";
        }
    }

This facade exposes only the operations the expression needs. Methods such as `capturePayment`, `refund`, `deleteOrder`, or `save` are excluded from the facade's API if the use case does not need them.

Prefer read-only or computational methods. If an expression genuinely needs to trigger an action, have the Java service validate permissions and orchestrate the action in an explicit step. Do not expose a generic method like `execute(String command)` or `invoke(String methodName, Object... args)` because it can turn the facade into an arbitrary invocation gateway.

## 5. Do not expose infrastructure beans or broadly privileged beans

The following objects are usually unsuitable to place into the context of untrusted expressions:

- ApplicationContext or BeanFactory.
- Generic repositories capable of reading or writing multiple entity types.
- Payment, money transfer, or account management services.
- Notification senders, mail senders, or message publishers.
- File system, process execution, or network clients.
- Security administration, user management, or permission services.
- Beans capable of resolving dependencies themselves or calling other services by name.

If an expression needs a result from these beans, compute the result in the Java layer and pass the required value into the context. If a controlled action is needed, expose a facade that performs only that exact action after the business layer has verified permissions.

## 6. Distinguishing bean references and variable references

Not every object an expression needs has to be referenced with `@beanName`. Objects or values can be passed through variables:

    context.setVariable("orderView", orderView);
    context.setVariable("discountRate", new BigDecimal("0.05"));

    #orderView.total * (1 - #discountRate)

Variables fit data for the current evaluation, whereas bean references fit capabilities or facades the expression is permitted to use.

| Syntax | Source | Recommended scope |
|---|---|---|
| `@pricing` | BeanResolver | Allowlisted facade or capability |
| `#orderView` | Variable in EvaluationContext | Data for the current evaluation |
| `property` | Root object | Data exposed by the root object |

If only a value such as a tax rate, display name, or status is needed, pass the value instead of exposing a service just to read one property. This makes expressions less coupled to the container and easier to test.

## 7. Preserving Spring-managed proxies and scopes

If a bean is proxied by Spring AOP, expose the bean instance returned by the container, keeping the proxy intact. Do not unwrap the proxy to retrieve the target object, because calls may need to pass through transactions, security interceptors, caching, or other advice.

For beans with request, session, or prototype scope, decide clearly how instances are obtained. Do not cache a short-lived instance inside a long-lived shared allowlist. You can create a resolver or context per request/use case so resolution adheres to the scope and lifecycle the application intends.

For expressions running across multiple tenants or multiple users, do not share an allowlist containing request-specific stateful objects. Create a context and facade suited to the principal, tenant, and purpose of that evaluation.

## 8. BeanResolver does not replace other restrictions

Restricting bean names is one layer of control. After a bean is resolved, the expression can still read properties or call methods allowed by the context. Therefore, simultaneously restrict:

- **Bean access:** which bean names can be resolved.
- **Method access:** which methods are permitted to be called on exposed objects.
- **Property access:** which properties can be read or written.
- **Evaluation features:** whether assignment, type references, constructor invocations, or bean references are allowed.
- **Input data:** whether variables, root object, and arguments come from trusted sources.

SimpleEvaluationContext is designed to restrict many SpEL features and does not support bean references. If the use case requires `@beanName`, an EvaluationContext supporting BeanResolver is usually needed, such as StandardEvaluationContext with a custom resolver. In that case, explicitly configure other capabilities rather than treating a BeanResolver allowlist as the sole line of defense.

## 9. Isolating contexts by use case

Each type of expression should receive its own context with the exact data and capabilities required. Example:

    EvaluationContext createPricingContext(OrderView order) {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("order", order);
        context.setBeanResolver(
                new AllowlistBeanResolver(
                        Map.of("pricing", pricingExpressionFacade)
                )
        );

        return context;
    }

This is an illustrative structure; the service creating the context must obtain the order and facade after verifying the corresponding access permissions. Do not share a single broadly privileged StandardEvaluationContext across all users or all expression types.

If an expression is only used to evaluate conditions, provide a read-only root object and avoid exposing beans with state-mutating methods. If another use case requires an action, create a separate context for that use case with a clear facade and policy.

## 10. Testing the allowlist

Test both allowed beans and rejected beans:

    context.setBeanResolver(
            new AllowlistBeanResolver(
                    Map.of("pricing", pricingExpressionFacade)
            )
    );

    parser.parseExpression("@pricing.getDefaultCurrency()")
            .getValue(context);

The call above can resolve the `pricing` bean. A reference like:

    @paymentService.refund(#order.id)

must be rejected if `paymentService` is not in the allowlist. In addition, verify that the facade does not expose out-of-scope methods, the resolver does not accidentally accept unintended aliases, and one tenant's context cannot resolve another tenant's capabilities.

For exposed methods, verify invocation count, argument types, results, and side effects. In particular, if an expression can be re-evaluated or retried, ensure the method does not cause unintended duplicate actions.

## 11. Takeaways

Do not expose the entire Spring BeanFactory to an expression if the use case only needs a few capabilities. Use an allowlist BeanResolver to restrict bean names, then expose a facade with a narrow API to restrict callable methods. Pass per-evaluation data via variables or the root object instead of opening a service just to read a value. Preserve Spring-managed proxies and scopes, isolate contexts by use case/tenant, and control property access, method invocation, and assignment alike. The presence of a bean in the container does not automatically place it within the permitted scope of every expression.
