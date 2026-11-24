# Root Object, Variables, and Bean Resolver in SpEL's EvaluationContext

EvaluationContext is what provides the data and mechanisms that Spring Expression Language (SpEL) needs when evaluating an expression. Among these, the **root object** is the default object for property lookups; **variables** are registered values referenced with the `#` prefix; and **BeanResolver** lets an expression retrieve beans by name using the `@beanName` syntax.

These three data sources serve different purposes. Distinguishing them clearly makes expressions easier to read, easier to test, and properly limits which objects or services an expression is allowed to use.

## 1. What does EvaluationContext provide?

When parsing a SpEL string, the parser produces an Expression. When evaluating the Expression, SpEL takes an EvaluationContext to know how to access objects and handle operations in the expression.

EvaluationContext can provide:

- Root object and active context object.
- Variables and functions.
- PropertyAccessor for reading or writing properties.
- MethodResolver for finding methods to invoke.
- BeanResolver for resolving beans by name.
- TypeLocator for finding classes in type references.
- TypeConverter for converting types.
- OperatorOverloader for customizing certain operations.

Not every expression needs all of these components. A simple property-reading expression may only need a root object; an expression using variables needs variables; an expression with `@beanName` needs a BeanResolver.

## 2. Setting the root object

The root object is the starting point when SpEL looks up a property or invokes a method without an explicitly specified target. With StandardEvaluationContext, you can pass the root object right when creating the context:

    Order order = loadOrder();

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    ExpressionParser parser = new SpelExpressionParser();

    String status = parser.parseExpression("status")
            .getValue(context, String.class);

In this example, `status` is looked up on the `order` object. There is no need to write `#order.status` because order is currently the root object.

You can change the root object after creating the context:

    context.setRootObject(anotherOrder);

Subsequent evaluations on that context will use the new root object. If a context is reused, pay attention to the current root state to avoid an expression accidentally running on an object from a previous processing pass.

You can also pass the root object directly when calling `getValue` using the appropriate overload. Whichever approach you use, clearly determine which object is the root in each evaluation.

## 3. Distinguishing #root and #this

SpEL provides two special variables:

- `#root` always references the initial root object of the evaluation.
- `#this` references the active context object at the point where the expression is currently being evaluated.

At the top level, `#this` usually matches the root object. When an expression enters collection selection or projection, the active context object switches to the element currently being processed, while `#root` remains unchanged.

Example:

    #root.items.?[
        price >= #root.minimumPrice
    ]

In the predicate:

- `#this` is the current item.
- `price` is looked up on the current item.
- `#root.minimumPrice` is read from the initial root object.

This can be written explicitly as:

    #root.items.?[
        #this.price >= #root.minimumPrice
    ]

Use `#root` when you need to refer back to the original object from inside a collection expression; use `#this` when you want to explicitly indicate the current object.

## 4. Registering and accessing variables

Variables are values supplied by the application to the EvaluationContext. With StandardEvaluationContext, use `setVariable(name, value)` to register them:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("discountRate", new BigDecimal("0.10"));
    context.setVariable("region", "VN");

In an expression, reference a variable with the `#` prefix:

    #discountRate
    #region
    total * (1 - #discountRate)

Example combining a root property with a variable:

    total * (1 - #discountRate)

Here `total` is read from the root object, while `#discountRate` is retrieved from the variable in the context.

You can register an object as a variable:

    context.setVariable("customer", customer);

    #customer.name
    #customer.getDisplayName()

A variable can be a String, number, Boolean, collection, or domain object. Choose appropriate data types and validate input data in Java before placing it into the context.

## 5. Properties, variables, and bean references are different

The three syntaxes below cannot be used interchangeably at random:

| Syntax | Data source | How it is provided |
|---|---|---|
| `status` | Property on the root or active context object | Set root object and configure PropertyAccessor |
| `#order` | Variable named order | `context.setVariable("order", order)` |
| `@orderService` | Bean named orderService in the Spring container | Configure BeanResolver |

Example:

    status == 'PAID'
    #order.status == 'PAID'
    @orderPolicy.isAllowed(#order)

The first line reads the `status` property on the root object. The second line reads the `order` variable, then accesses that object's property. The third line resolves the `orderPolicy` bean and calls a method on the bean.

If an expression reports that a property or variable cannot be found, check the correct reference source: root object, variable, or bean. Do not add a `#` or `@` prefix at random just to try it out; each prefix has a distinct resolution mechanism.

## 6. Configuring BeanResolver to use @beanName

A standalone StandardEvaluationContext does not automatically know about the Spring ApplicationContext. To use the `@beanName` syntax, a BeanResolver must be registered.

Spring provides `BeanFactoryResolver` to connect EvaluationContext with a BeanFactory:

    ConfigurableApplicationContext applicationContext =
            ...;

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setBeanResolver(
            new BeanFactoryResolver(
                    applicationContext.getBeanFactory()
            )
    );

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal total = parser.parseExpression(
            "@pricingService.calculateTotal(#root)"
    ).getValue(context, BigDecimal.class);

During evaluation, BeanFactoryResolver looks up the `pricingService` bean by name. The expression can read properties or call methods on the bean after successful resolution.

Without a BeanResolver, a manually created context cannot resolve `@pricingService`. Creating a SpelExpressionParser does not automatically link the parser to a BeanFactory.

## 7. Combining root object, variables, and bean resolver

An expression can use all three sources within the same evaluation:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "discountRate",
            new BigDecimal("0.05")
    );

    context.setVariable("customer", customer);

    context.setBeanResolver(
            new BeanFactoryResolver(beanFactory)
    );

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal discount = parser.parseExpression(
            "@pricingService.calculateDiscount(" +
            "#root.total, #customer.level, #discountRate)"
    ).getValue(context, BigDecimal.class);

In the example:

- `#root` is the order passed when creating the context.
- `#customer` and `#discountRate` are registered variables.
- `@pricingService` is the bean resolved from the BeanFactory.

Arguments are evaluated in the current context before the method is invoked. Argument types and the method signature must be compatible; the context's TypeConverter can assist with conversion when needed.

## 8. Bean reference vs. a variable holding a service

You can pass a service into the context as a variable:

    context.setVariable("pricingService", pricingService);

    #pricingService.calculateTotal(#root)

This approach differs from a bean reference:

    @pricingService.calculateTotal(#root)

The `#pricingService` form retrieves the object from variables. The `@pricingService` form requires BeanResolver to look up the bean by name in the container.

Use a variable when the application wants to supply a specific object for a single evaluation or isolated context. Use a bean reference when you want the expression to use a Spring-managed component. Do not register the same object in multiple ways if it makes it hard for readers to tell which source the expression is using.

## 9. StandardEvaluationContext and SimpleEvaluationContext

StandardEvaluationContext provides a fuller SpEL feature set, including support for working with properties, methods, types, constructors, and a bean resolver when configured. It is a flexible choice for trusted internal expressions.

SimpleEvaluationContext limits the feature set to better fit data binding and use cases requiring narrow permissions. It does not support type references, constructor invocations, or bean references. Instance method invocation is also not enabled by default; it can be explicitly configured via the builder using `withInstanceMethods()` when a use case requires it.

Read-only context example:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

This context is suitable when an expression only needs to read data via data binding. If an expression needs `@beanName`, you must use an EvaluationContext type that supports BeanResolver and intentionally configure access permissions.

Do not switch to StandardEvaluationContext just to make an expression run if the expression comes from a user or a source that is not fully trusted. Choose the context according to the exact capabilities that need to be provided.

## 10. Isolating context per processing pass

A parsed Expression can be reused, but data in an EvaluationContext can change. Root objects, variables, and resolvers are part of the context's configuration or state.

In an application handling multiple requests, create an appropriate context for each request or each use case:

    EvaluationContext createContext(
            Order order,
            Customer customer,
            BeanFactory beanFactory) {

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable("customer", customer);
        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );

        return context;
    }

This is an illustrative structure. The service creating the context must verify that the caller is authorized to access the corresponding order and customer before placing them into the context.

Avoid changing the root object or variables on a shared context across concurrent requests. Doing so can cause one evaluation to see data from another request. Keep context configuration and data aligned with the lifecycle of the use case.

## 11. Restricting exposed beans and data

BeanResolver can open access to beans in the container. If an expression is not fully trusted, you should not expose the entire BeanFactory by default without restrictions.

Some principles:

- Only provide beans that the expression genuinely needs.
- Prefer a facade with a narrow API rather than a large service with many public methods.
- Do not expose ApplicationContext or BeanFactory as an object for expressions to discover dependencies on their own.
- Do not put repositories, payment services, or administrative services into the context if the use case does not need them.
- Verify data access permissions before placing objects into root or variables.
- Restrict method invocation, property access, and assignment according to the intended use.

If only a few beans are needed, you can use a custom BeanResolver to allowlist resolvable names. Even so, a bean allowlist does not replace restricting methods and properties on the exposed objects.

## 12. Debugging root, variable, and bean resolution errors

When an expression fails to resolve a reference, identify the exact mechanism being used:

1. For properties without a prefix, check the root object or active context object and PropertyAccessor.
2. For `#name`, check whether the variable has been registered with the exact name.
3. For `@name`, check whether BeanResolver is configured and whether BeanFactory has the corresponding bean or alias.
4. For nested properties, check whether intermediate objects are null.
5. For methods on a bean or variable, check the method name, accessibility, and argument types.

You can inspect variables in Java:

    Object customerValue = context.lookupVariable("customer");

    System.out.println(
            customerValue == null
                    ? "null"
                    : customerValue.getClass().getName()
    );

For the root object, check the object passed into the context or the value returned by `getRootObject()`. For beans, check BeanFactory and the resolver at the configuration layer instead of repeatedly changing the expression.

Do not catch every resolution error and return null as if the data did not exist. Errors can stem from a misconfigured context, a wrong bean name, or a bean initialization failure; preserve enough error information for diagnosis.

## 13. Key takeaways

EvaluationContext provides the root object, variables, and resolvers that SpEL needs during evaluation. Use direct property names to access the root or active context object; use `#variable` for data registered via `setVariable`; use `@beanName` when BeanResolver connects the context to the Spring container. `#root` keeps the initial root object, while `#this` is the active context object and can change inside collection expressions. StandardEvaluationContext supports more features; SimpleEvaluationContext restricts capabilities for data binding. Create contexts per use case, expose only necessary objects and beans, and verify permissions before supplying data to expressions.
