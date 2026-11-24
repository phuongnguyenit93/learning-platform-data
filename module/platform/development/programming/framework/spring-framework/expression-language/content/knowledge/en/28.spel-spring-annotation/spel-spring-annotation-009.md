# Identifying the EvaluationContext provided by each Spring module

## 1. Why does each module have its own EvaluationContext?

Spring Expression Language (SpEL) provides a shared parser and expression evaluation engine. However, when a Spring annotation or module supports SpEL, that module usually creates or configures an EvaluationContext tailored to its purpose.

EvaluationContext determines what the expression can see and what it is allowed to do. A context can provide:

- A root object to resolve unprefixed properties and methods.
- Variables referenced with the # prefix.
- PropertyAccessor to read or write properties according to the module's rules.
- MethodResolver and ConstructorResolver to find methods or constructors.
- BeanResolver to access beans using the @beanName syntax.
- TypeLocator to resolve classes in T(...) expressions.
- TypeConverter to convert values when assigning properties, calling methods, or retrieving results.

Therefore, an expression may work at one integration point yet fail at another. For example, a bean reference might work in a BeanFactory expression but be unavailable in a manually created context. A #result variable might be provided by the cache expression evaluator but not exist in @Value's context.

There is no single EvaluationContext that automatically applies to every Spring annotation. To know what a specific expression sees, identify which module processes that annotation and what context that module creates.

## 2. Distinguishing parser, Expression, and EvaluationContext

These three components have different responsibilities:

| Component | Responsibility |
|---|---|
| ExpressionParser | Parses source into an Expression structure |
| Expression | Holds the parsed expression and provides getValue/setValue |
| EvaluationContext | Provides root object, variables, accessors, resolvers, and conversion rules at evaluation time |

Example using a manually created context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customer.name");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

String name = expression.getValue(context, String.class);
~~~

The parser does not decide what object customer is. EvaluationContext holds the root object order; the context's property accessor reads customer and name when the expression is evaluated.

A parser can be reused with multiple contexts. The same Expression can yield different results when the root object or variables change. When a Spring annotation evaluates an expression, the integration module typically owns the step of creating the context and passing it to the expression evaluator.

## 3. How to find the EvaluationContext of an annotation

When encountering an annotation with an attribute accepting SpEL, trace the component responsible for processing that annotation. Do not infer the context solely from the expression syntax.

A practical workflow:

1. Identify which module the annotation belongs to, such as core container, cache, method security, Spring Data, or events.
2. Find the processor, interceptor, expression evaluator, or handler that processes the annotation.
3. Locate where parseExpression and evaluate/getValue are called.
4. Check where the context is created, what type the root object has, and which variables are placed into the context.
5. Check whether BeanResolver, TypeConverter, PropertyAccessor, and other resolvers are configured.
6. Write a small test at the exact integration point to confirm which variables and objects are actually available.

Class names can change between Spring versions and between modules. Look up the source code of the exact dependency running in the application, rather than taking a class name from an example for another version and assuming it is still accurate.

## 4. @Value and the BeanFactory expression context

In the Spring Framework core container, @Value and expressions in bean definitions are processed through BeanFactory's expression mechanism. ConfigurableBeanFactory has a BeanExpressionResolver; the common default implementation is StandardBeanExpressionResolver.

This resolver creates an EvaluationContext based on BeanFactory's BeanExpressionContext. The context is typically configured to access container capabilities such as beans, environment, and scoped objects.

Example:

~~~java
@Component
public class WelcomeMessage {
    @Value("Hello #{systemProperties['user.name']}")
    private String message;

    @Value("#{T(java.lang.Math).max(3, 5)}")
    private int limit;

    @Value("#{applicationProperties['region']}")
    private String region;
}
~~~

Expressions in @Value are evaluated in the context provided by the Spring container. Bean references can be written using @beanName when the resolver has an appropriate BeanResolver. Property access can also be extended to read data from BeanExpressionContext, BeanFactory, Map, or Environment.

Do not treat the example above as a complete list of variables available for every BeanFactory or every configuration. Check the specific resolver and BeanFactory of your application. With a context created manually via new StandardEvaluationContext(), these capabilities do not appear automatically.

If you need to evaluate expressions manually with the same capabilities as @Value, explicitly configure the root object, BeanResolver, TypeConverter, PropertyAccessor, and required variables. In many cases, using the Spring container itself to test @Value is more reliable than trying to reconstruct resolver internals in a unit test.

## 5. Method security: @PreAuthorize and @PostAuthorize

Spring Security method security has its own expression handler. Under standard method security configuration, DefaultMethodSecurityExpressionHandler creates the context and security expression root for method invocations.

Commonly used annotations:

- @PreAuthorize: checks conditions before the method runs.
- @PostAuthorize: checks conditions after the method returns.
- @PreFilter: filters a collection argument before the method runs.
- @PostFilter: filters the returned collection or specified collection after the method runs.

Example:

~~~java
@PreAuthorize("hasAuthority('invoice:read')")
public Invoice findInvoice(Long id) {
    return repository.findById(id).orElseThrow();
}

@PostAuthorize("returnObject.owner == authentication.name")
public Invoice loadOwnedInvoice(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

The security context provides a specialized root object, typically having capabilities such as hasRole, hasAuthority, authentication, principal, permission checks, and bean references when configured. Method arguments are placed into the evaluation context by parameter name if discoverable, and can also be referenced using aliases like #p0 or #a0.

In @PostAuthorize, the method result can be referenced via returnObject or #returnObject depending on the handler's syntax and context. In @PreFilter/@PostFilter, filterObject represents the current element being filtered. These variables are meaningful per annotation and execution timing; do not assume they are always present in every security expression.

If replacing MethodSecurityExpressionHandler or configuring a custom root object, the set of helpers and variables may differ. Check the actual handler registered in the application.

## 6. Cache annotations: @Cacheable, @CachePut, and @CacheEvict

Spring Cache has its own expression evaluator for cache annotations. Cache operation expressions are usually evaluated with a root object describing the method invocation and related caches.

Example:

~~~java
@Cacheable(
        cacheNames = "products",
        key = "#root.methodName + ':' + #id",
        condition = "#id != null",
        unless = "#result == null")
public Product findProduct(Long id) {
    return repository.findById(id).orElse(null);
}
~~~

In cache expressions, the root object typically provides information such as method, target, targetClass, arguments, and caches. Method arguments can be accessed by parameter name if names are retained or by aliases such as #p0 and #a0.

#result is used at stages where the method result already exists, such as the unless condition of @Cacheable. Not every cache attribute is evaluated after the method runs. For example, condition and key are usually computed before invocation, so they cannot rely on a method result that does not exist yet.

With @CacheEvict, the beforeInvocation attribute affects eviction timing. An expression cannot read the method result before the method is called. Determine when the evaluator runs before using #result or result-dependent variables.

## 7. Spring Data repository query expressions

Spring Data has EvaluationContextProvider and extension components to build contexts for SpEL in repository queries. Exact syntax depends on the Spring Data module and repository type.

Example in Spring Data JPA:

~~~java
@Query("select u from User u where u.firstname = ?#{[0]}")
List<User> findBySpelArgument(String firstname);
~~~

Spring Data JPA also supports the #entityName variable in query templates:

~~~java
@Query("select e from #{#entityName} e where e.active = true")
List<?> findAllActive();
~~~

Repository query contexts can provide method arguments, parameter names, entity metadata, and registered extensions. An extension can add a root object or variables; for example, Spring Security integration can provide user information if the corresponding extension is added to the configuration.

Do not assume a variable appears merely because the application has the corresponding dependency on the classpath. The extension must be supported by the module and registered in the way EvaluationContextProvider uses. Check the active Spring Data configuration and write repository integration tests for query expressions.

## 8. @EventListener condition

@EventListener has a condition attribute allowing SpEL to decide whether the listener is called:

~~~java
@Component
public class OrderEvents {

    @EventListener(condition = "#event.status == 'PAID'")
    public void onOrderChanged(OrderChangedEvent event) {
        // Handle paid event.
    }
}
~~~

Event listener expressions are evaluated in a context created by Spring's event annotation mechanism. The context may expose the event and method arguments in the root object or variables for the expression to access. Naming and aliases depend on the evaluator and Spring version.

Therefore, verify references such as #root, #event, #a0, or parameter names against the source code and integration tests of the version in use. Do not assume @EventListener's context matches @Value's or method security's context just because all three use SpEL.

## 9. Scoped values and annotations using @Value

Some Spring modules or scopes allow @Value to reference data only available within a specific scope. For example, Spring Batch late binding often uses step-scoped or job-scoped beans to read job parameters and execution context:

~~~java
@Bean
@StepScope
public ItemReader<InputRecord> reader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return createReader(inputFile);
}
~~~

Here the expression is evaluated within the relevant bean scope lifecycle. Objects such as jobParameters are exposed by Spring Batch's scope mechanism and BeanFactory integration.

If moving the same expression to an ordinary singleton bean or a manually created StandardEvaluationContext, jobParameters may not exist. Variable availability depends on the active scope and resolver, not solely on the expression content.

When testing late binding, run tests with Spring Batch's appropriate StepScope or JobScope test support to simulate the required context.

## 10. Comparing common contexts

| Integration point | Component to trace | Typically exposed data |
|---|---|---|
| @Value / bean definition | BeanExpressionResolver, usually StandardBeanExpressionResolver | BeanFactory, Environment, system properties/environment, and scope context |
| @PreAuthorize / @PostAuthorize | MethodSecurityExpressionHandler | Security root, authentication, method arguments, permissions, and security helpers |
| @PreFilter / @PostFilter | Method security expression handler | Security root, filterObject, and collection being filtered |
| @Cacheable / @CachePut / @CacheEvict | CacheOperationExpressionEvaluator | Method, target, targetClass, args, caches, and result depending on timing |
| Spring Data query | Module's EvaluationContextProvider and query evaluator | Method arguments, entity metadata, and registered extensions |
| @EventListener condition | Event expression evaluator | Event and method arguments per listener context |
| Spring Batch late binding | Scope context combined with BeanFactory expression resolution | jobParameters, jobExecutionContext, or stepExecutionContext by scope |

This table is a navigation map to find the right implementation location. The exact set of variables and root object type can vary by module, configuration, and version.

## 11. The same expression does not guarantee the same result across modules

Suppose an expression uses #result:

~~~text
#result == null
~~~

This expression is meaningful when the evaluator provides the result variable at evaluation time, such as certain cache operations after the method returns or security post-invocation expressions. In a context without a result variable, the expression may return null or behave differently from what the author expected.

Similarly, #root.method may exist in cache expressions but not have the same structure in @Value's context. The authentication variable may be exposed by a security handler or extension, yet not appear automatically in a standalone SpEL context.

When reusing expressions across modules, list their dependencies: root properties, variables, bean references, method calls, and conversion rules. Then confirm each context supplies all of those dependencies.

## 12. How to inspect the root object and variables while debugging

When an expression produces unexpected results, inspect the context at the exact evaluation point:

1. Set a breakpoint at the expression evaluator or handler processing the annotation.
2. Inspect the root object and the runtime type of the root object.
3. Check the list of variables placed into the context.
4. Inspect property accessors and method resolvers.
5. Check whether BeanResolver is configured if the expression uses @beanName.
6. Check TypeConverter and ConversionService if type conversion occurs.
7. Determine whether the expression is evaluated before or after method invocation.

Not every EvaluationContext has an API to list all variables uniformly. If you need to observe variables, inspect where the context is created and where setVariable or extensions are called there. You can add logging or breakpoints in integration code while running tests.

## 13. Testing the right module instead of testing only the parser

A unit test calling SpelExpressionParser and StandardEvaluationContext verifies basic SpEL syntax and behavior. It does not prove that the annotation integration creates the right context.

Test at the right layer:

- For @Value, initialize an ApplicationContext and verify the bean receives the right value.
- For method security, invoke the method through a Spring proxy and verify access according to current authentication.
- For cache annotations, invoke the method through a proxy and verify key, condition, or unless based on the method result.
- For Spring Data, execute an actual repository query and verify parameters/metadata.
- For @EventListener, publish an event and verify the condition decides whether the listener runs.
- For Spring Batch, run tests within the appropriate StepScope or JobScope.

These integration tests confirm the module created the context, root object, variables, and resolvers as desired. Parsing the expression in isolation cannot verify those steps.

## 14. When a context is missing a variable or bean

If an expression references a variable that is not provided, lookup may return null or cause an error in subsequent operations. If using a bean reference @service when BeanResolver is absent or the bean is not found, evaluation may fail.

How to handle:

- Determine whether the module promises to provide that variable or bean reference.
- Check extension, resolver, and bean registration configuration.
- If the variable is an application input, pass it explicitly via the context or root object.
- If logic exists in only one module, keep the expression within that module rather than reusing it where the same context does not exist.
- Write tests for missing-variable cases to clearly decide between a default result or a configuration error.

Do not hide configuration errors by adding an Elvis default to every variable. Default values are only appropriate when they are a business rule; if a required variable is missing, a clear error is usually easier to diagnose.

## 15. Security and permissions of EvaluationContext

EvaluationContext not only determines what data an expression sees, but also what capabilities an expression can use. A context may allow calling methods, referencing beans, resolving types, or reading sensitive properties.

Some principles:

- Do not evaluate arbitrary user-submitted templates or expressions with a broad-permission context.
- Expose only the beans and methods necessary for the expression.
- Use a restricted context such as SimpleEvaluationContext when the need is only controlled data binding or property access.
- For method security, keep the handler and root object designed for security; do not replace them with a custom context that bypasses permission checks.
- Do not place secrets or sensitive objects into the root object if the expression does not need to access them.

Even a short expression can call a method with side effects if the context allows it. Treat the context as part of the security boundary and test actual permissions, not just string output.

## 16. Common mistakes

**Assuming every annotation uses the same context**

Modules have their own evaluators, root objects, and variables. Find the annotation's exact handler.

**Confusing root properties with variables**

Root properties are accessed directly by name; variables typically have the # prefix. These two sources are not interchangeable.

**Using #result before the result exists**

Some expressions run before method invocation. Check the lifecycle of the cache/security operation before referencing the result.

**Assuming bean references are always available**

The @beanName syntax requires an appropriate BeanResolver. A manually created context does not automatically know about the ApplicationContext.

**Testing only with SpelExpressionParser**

Parser tests do not run annotation processors, AOP proxies, repository evaluators, or event listeners. Add integration tests for the relevant module.

**Using variables from another module without registering the extension**

Spring Data or other modules may provide extensions depending on configuration. Having a dependency on the classpath does not automatically guarantee the extension is registered.

**Looking up source from a different version**

Handler names, evaluators, and variable details can change. Check the exact Spring Framework, Spring Security, Spring Data, or Spring Batch version of your application.

## 17. Comprehensive example: same data, two contexts

An Order object can be used in a manually created context:

~~~java
Order order = new Order("ORD-1001", "Lan");

StandardEvaluationContext manualContext =
        new StandardEvaluationContext(order);
manualContext.setVariable("prefix", "Order");

Expression expression =
        new SpelExpressionParser().parseExpression(
                "#prefix + ': ' + code + ' / ' + customerName");

String result = expression.getValue(manualContext, String.class);
~~~

In the manually created context, code must actively provide the root object and the prefix variable. If the expression needs bean references or a special helper, code must also configure the corresponding resolvers.

When the same string is used in an annotation of another module, that module creates a context according to its own contract. The root object may no longer be Order, the prefix variable may not exist, or special variables such as #result or #filterObject may be added. An expression can only be safely reused when the two contexts have the same data contract and access permissions.

## 18. Key takeaways

- EvaluationContext determines the root object, variables, property accessors, method resolvers, bean/type resolvers, and TypeConverter.
- Parser creates Expression; context provides the environment when Expression is evaluated.
- There is no universal EvaluationContext for every Spring annotation.
- @Value typically goes through BeanFactory's BeanExpressionResolver, commonly StandardBeanExpressionResolver.
- Method security uses MethodSecurityExpressionHandler and a dedicated security expression root.
- Cache annotations use a cache expression evaluator with a root containing method, target, arguments, caches, and result depending on timing.
- Spring Data queries and @EventListener have their own evaluators/contexts; check extensions and method argument exposure.
- Spring Batch late binding depends on scope context such as job parameters and execution context.
- Locate the evaluator, where the context is created, and where variables are set in the exact dependency version.
- Test through the annotation/module itself; parser unit tests do not replace integration tests.
- Do not assume variables or beans from one module exist in another module's context.
- EvaluationContext permissions are part of security design.
