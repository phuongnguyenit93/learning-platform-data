# Bean References with @beanName in SpEL

Spring Expression Language (SpEL) allows referencing beans managed by the Spring container using the `@beanName` syntax. Once the bean is obtained, the expression can read properties or call methods on that bean just like with a regular object. This capability helps expressions connect with services, components, or configuration objects in the application.

For the reference to work, the EvaluationContext must have a BeanResolver that knows how to look up beans by name. A standalone StandardEvaluationContext does not automatically know about the application's ApplicationContext or BeanFactory. Therefore, an appropriate resolver must be configured before evaluating an expression containing `@beanName`.

## 1. Bean reference syntax

Basic syntax:

    @beanName

Examples:

    @pricingService
    @messageSource
    @orderPolicy

SpEL interprets `@pricingService` as a reference to the bean named `pricingService` in the container. The result is the bean object, not the string literal "pricingService".

You can continue reading properties or calling methods on the bean:

    @pricingService.defaultCurrency
    @pricingService.calculateDiscount(#order)
    @messageSource.getMessage('order.created', null, null)

In the last example, SpEL retrieves the messageSource bean and then calls the `getMessage` method with the corresponding arguments. The bean is looked up by name at the time the expression is evaluated.

The `@` symbol here is SpEL syntax for referencing a bean. It is not a Java annotation like `@Component` or `@Service`; those annotations typically help Spring register beans, whereas `@beanName` uses a bean already managed by the container inside an expression.

## 2. Configuring BeanResolver for StandardEvaluationContext

In a manually created EvaluationContext, a BeanResolver must be registered. Spring provides `BeanFactoryResolver` to connect SpEL with a BeanFactory:

    ConfigurableApplicationContext applicationContext =
            ...;

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setBeanResolver(
            new BeanFactoryResolver(
                    applicationContext.getBeanFactory()
            )
    );

    ExpressionParser parser = new SpelExpressionParser();

    Object result = parser.parseExpression(
            "@pricingService.defaultCurrency"
    ).getValue(context);

`BeanFactoryResolver` is in the `org.springframework.context.expression` package. It takes a BeanFactory and uses that factory to look up beans by name when SpEL asks to resolve a bean reference.

If a BeanFactory is already available, it can be passed directly into the constructor. With an ApplicationContext, the BeanFactory can be obtained through the appropriate API of the context in use.

If BeanResolver configuration is omitted, a plain StandardEvaluationContext cannot automatically resolve `@pricingService`; evaluating the expression will fail because there is no resolver to look up the bean. Creating a parser does not automatically connect the parser to the Spring container.

## 3. Using a bean reference to call methods

Once the bean is resolved, methods can be called on the bean:

    @pricingService.calculate(#order.subtotal, #customer.level)

Suppose the `pricingService` bean has a method taking two corresponding arguments. SpEL will:

1. Resolve the `pricingService` bean through the BeanResolver.
2. Evaluate the arguments `#order.subtotal` and `#customer.level`.
3. Resolve the `calculate` method matching the target and argument types.
4. Call the method and return the resulting value.

Example in Java:

    context.setVariable("order", order);
    context.setVariable("customer", customer);

    BigDecimal discount = parser.parseExpression(
            "@pricingService.calculate(#order.subtotal, #customer.level)"
    ).getValue(context, BigDecimal.class);

The variables `order` and `customer` must be registered in the context. The `pricingService` bean is looked up by name in BeanFactoryResolver; it does not need to be registered as a separate SpEL variable.

No-argument methods can be called:

    @featureFlags.isNewCheckoutEnabled()

Or properties can be read:

    @applicationSettings.defaultLocale

Ensure that the method/property actually exists and the result type matches where the expression is used.

## 4. Bean names with dots or special characters

Bean names are usually simple identifiers, such as `pricingService`. If a bean name contains dots or characters that need explicit delimiting, the bean name can be placed inside single quotes after `@`:

    @'legacy.pricing.service'

This notation helps the parser treat the entire quoted portion as the bean name. The name in the expression must match the bean name or alias registered by the container.

When possible, use short, meaningful bean names that do not require escaping. Consistently named beans make expressions easier to read and avoid errors caused by names containing special characters.

## 5. Referencing a FactoryBean with the & prefix

Spring has a special type of bean called `FactoryBean`. When looking up a FactoryBean name normally, the container returns the object created by the factory. If you need to access the factory object itself, use the `&` prefix:

    @myProduct
    @&myProduct

- `@myProduct` references the product created by the FactoryBean.
- `@&myProduct` references the FactoryBean itself.

For example, if `reportFactory` is a FactoryBean that creates a ReportExporter:

    @reportFactory.exportFormat
    @&reportFactory.getObjectType()

The first expression works with the product provided by the factory; the second expression works with the factory object. Only use the `&` symbol when you actually need to operate on the FactoryBean, not its product.

## 6. Bean aliases, scopes, and proxies

BeanResolver uses bean names through the BeanFactory. If the container registers aliases, an alias can also be used to resolve the bean according to the factory's rules.

The returned result depends on the bean's scope:

- **Singleton:** repeated resolutions typically return the same singleton instance managed by the container.
- **Prototype:** each resolution by the BeanFactory may create a new instance.
- **Request or session scope:** resolution depends on an active request/session and may fail if the scope is not active.

A lazy-init bean may be initialized when it is resolved for the first time. Therefore, simply evaluating an expression can trigger bean initialization.

If a bean is proxied by Spring AOP, BeanFactoryResolver normally returns the object managed by the container, which is the proxy when the bean is proxied. Method calls via the bean reference will go through the proxy and its corresponding interceptors. You should not manually unwrap the target object inside the proxy if you want to preserve transaction, security, or advice behaviors managed by Spring.

## 7. Bean references in Spring configuration expressions

In places where the Spring container manages bean expression evaluation itself, the framework can provide an appropriate BeanResolver. For example, an expression in the `@Value` annotation can reference a bean:

    @Value("#{ @pricingService.defaultCurrency }")
    private String currency;

Or call a method:

    @Value("#{ @featureFlags.isNewCheckoutEnabled() }")
    private boolean newCheckoutEnabled;

Expressions like these are handled by Spring within the container's bean expression environment. That configuration differs from manually creating a StandardEvaluationContext in Java; for a manually created context, register the BeanResolver as shown in the previous section.

Do not confuse the `@Value` annotation with the `@beanName` syntax: `@Value` is a Spring annotation for injecting values, while `@pricingService` inside the SpEL string is a bean reference.

## 8. Separating bean references from variables in EvaluationContext

Both bean references and variable references can return objects, but they are resolved differently:

| Syntax | Data source | Registration method |
|---|---|---|
| `@pricingService` | Bean by name in the Spring container | BeanResolver |
| `#pricingService` | Variable in EvaluationContext | `context.setVariable(...)` |
| `customer` | Property on the root object | Root object and PropertyAccessor |

Example:

    context.setVariable("calculator", calculator);

    #calculator.calculate(10)

The call above uses a variable placed into the context by the application. Meanwhile:

    @calculator.calculate(10)

requires the container to have a bean named `calculator` and a configured BeanResolver.

Use a bean reference when you want the expression to access a Spring-managed component. Use a variable when you want to provide a specific object for a single evaluation or a specific context. Avoid registering the same object under multiple reference mechanisms if doing so makes the expression harder to understand.

## 9. Restricting accessible beans

Bean references can open up access to components in the application. If expressions come from users or not fully trusted sources, providing a BeanFactoryResolver for the entire BeanFactory can expose too many beans.

For example, if the context can resolve every bean, an expression author might try referencing repositories, administrative services, or components with methods that have side effects. Just because a bean can be resolved does not mean every method of that bean is appropriate to call from an expression.

Several principles should be applied:

- Only bring necessary beans into the expression's scope.
- Consider a custom BeanResolver that only resolves names in an allowlist.
- Prefer a facade with a narrow API instead of directly exposing a service with broad privileges.
- Avoid providing repositories, payment gateways, notification senders, or administrative services to untrusted expressions.
- Combine bean restrictions with restrictions on method invocation, property access, and write permissions.
- Validate inputs and business permissions in the service; do not rely on the expression to enforce authorization on its own.

A custom BeanResolver can check the bean name before returning an object. If the name is not allowed, the resolver should explicitly reject it instead of returning an arbitrary object. The allowlist must be defined in trusted configuration code, not taken from the expression content.

## 10. Handling errors when resolving beans

A bean reference can fail in the following situations:

- There is no BeanResolver in the EvaluationContext.
- The bean name or alias does not exist.
- The FactoryBean does not provide the expected product.
- The bean belongs to request/session scope, but the scope is not active.
- Bean initialization fails due to dependencies or configuration.
- The bean is resolved, but the invoked method/property does not exist or is inaccessible.

When debugging, separate bean resolution errors from method invocation errors. First confirm that the BeanResolver is registered and the bean name exists in the BeanFactory. Then check the method signature, argument types, scope, and underlying error during execution.

Do not catch all errors and return null as if the bean simply did not exist normally. That can hide important configuration or initialization errors. Handle errors according to the application's error policy and provide appropriate diagnostic information.

## 11. Takeaways

The `@beanName` syntax references a bean by name in the Spring container. In a manually created StandardEvaluationContext, `BeanFactoryResolver` must be registered using `setBeanResolver(...)` so SpEL can look up beans. After resolution, properties can be read or methods called on the bean like a regular object. Use `&beanName` when the FactoryBean itself is needed instead of its product. Bean scope, lazy initialization, and AOP proxies remain managed by the container. Because bean references can open access to services and methods with side effects, restrict exposed beans and only allow operations appropriate for the expression's purpose.
