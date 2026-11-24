# Bean Initialization Order and Expression Evaluation in Spring

In Spring, when a Spring Expression Language (SpEL) expression is evaluated depends on where the expression is used. Expressions in bean definitions or `@Value` are typically evaluated while the container is creating the bean and populating its dependencies. Expressions in method security are evaluated when the method is called. For SpEL used directly in Java, the application decides when to call `getValue()`.

Therefore, expression evaluation is not an independent step that always runs at the beginning or end of startup. It happens at the point where Spring or the application needs the expression's value. If an expression references a bean with `@beanName`, that resolution can also trigger the creation of the referenced bean.

## 1. Overview of ApplicationContext Refresh

When an ApplicationContext is refreshed, Spring prepares the BeanFactory, processes bean definitions, and registers infrastructure components before instantiating most regular singletons.

The main phases can be envisioned as follows:

1. Create or load the BeanFactory and BeanDefinitions.
2. Run BeanFactoryPostProcessor and BeanDefinitionRegistryPostProcessor to adjust bean metadata.
3. Register BeanPostProcessors to participate in bean creation.
4. Instantiate remaining eager singletons during the refresh completion phase.
5. Emit initialization callbacks, finish refresh, and publish context readiness.

This is the general order; some infrastructure beans are created earlier to serve those very phases. Not all beans are created at the same time, and lazy beans may only be created on first access.

SpEL can be evaluated at multiple points in this sequence. For example, a SpEL value in a bean definition may be resolved when that bean is created; `@Value` is resolved during dependency injection; and an expression in `@PreAuthorize` is only evaluated when method security handles a method invocation.

## 2. Lifecycle of a Regular Bean

For a bean created during startup, the sequence typically consists of these steps:

1. **Instantiate:** call a constructor or factory method to create the instance.
2. **Populate properties:** assign properties and perform dependency injection, including field/setter injection.
3. **Aware callbacks:** invoke callbacks such as `BeanNameAware`, `BeanClassLoaderAware`, and `BeanFactoryAware` when the bean implements the corresponding interfaces.
4. **Before-initialization post-processors:** run BeanPostProcessors before init callbacks.
5. **Initialization callbacks:** invoke `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom init methods according to the configured lifecycle mechanism.
6. **After-initialization post-processors:** run BeanPostProcessors after init; processors may return a proxy instead of the original instance.

Specific details depend on the bean type and configuration, but the key point is that dependency injection and the values needed by the bean are processed before init callbacks.

An expression used to provide a value for a bean's field or setter is usually evaluated during the populate properties phase. Thus, init methods can read the injected value. If the expression calls another bean, that bean may be resolved and created before the current bean finishes initializing.

## 3. SpEL in Bean Definitions

Spring supports expressions in bean definition values. XML example:

    <bean id="serviceConfig"
          class="com.example.ServiceConfig">
        <property name="timeout"
                  value="#{systemProperties['service.timeout']}" />
    </bean>

When the container needs to create the bean and set properties, BeanFactory uses BeanExpressionResolver to evaluate the expression. The result is converted to the property type if needed before being written.

In Java configuration, SpEL can be used in values resolved by the container, such as through `@Value` or corresponding configuration mechanisms. Do not confuse expression parse time with bean creation time: the container may parse/cache expressions beforehand, but the value is still evaluated when resolution is needed for the bean.

If an expression in a bean definition references another bean, for example `@pricingPolicy.defaultRate`, the resolver needs to retrieve that bean from BeanFactory. This resolution may cause the bean to be created earlier than its normal turn in the pre-instantiation flow.

## 4. When @Value Is Evaluated

`@Value` can contain a property placeholder or SpEL:

    @Value("${app.region}")
    private String region;

    @Value("#{systemProperties['user.timezone']}")
    private String timeZone;

Placeholder `${...}` retrieves a value from configuration sources registered with Spring. SpEL `#{...}` evaluates an expression. Both mechanisms can be combined in the same configuration, but they have different purposes.

With field or setter injection, `@Value` is processed during the populate properties phase by a dedicated BeanPostProcessor. The value is resolved before the bean's init callbacks run.

With constructor parameters:

    public ReportService(
            @Value("${reports.default-format}") String format) {
        this.format = format;
    }

Spring must resolve the argument before calling the constructor. If a constructor parameter expression references another bean, the referenced bean may have to be resolved before the ReportService instance is created.

A `@Value` value is typically injected at bean creation time. If the property source changes afterward, the injected field is not automatically recomputed. For dynamic configuration, use a configuration management mechanism or a bean with appropriate update behavior.

## 5. Bean References Can Trigger Creation of Other Beans

In an expression:

    @Value("#{ @pricingPolicy.defaultRate }")
    private BigDecimal defaultRate;

Spring needs to resolve the bean named `pricingPolicy` to read the `defaultRate` property. If that bean does not exist yet and is a bean to be created on demand, BeanFactory may initialize it immediately while creating the current bean.

This has several consequences:

- The referenced bean may be initialized earlier than expected.
- The constructor, dependency injection, init callbacks, and BeanPostProcessors of the referenced bean may run nested inside the current bean's creation.
- If the referenced bean depends back on the current bean, a circular dependency may arise.
- If the bean has side effects in its constructor or init callbacks, those side effects also happen when the expression is resolved.

Therefore, use bean references in SpEL for values or calculations with clear scope. Avoid calling methods that start workflows, write data, or perform I/O in expressions used to inject a configuration value.

## 6. Expressing Dependencies and Initialization Order Explicitly

If bean A truly depends on bean B, dependency injection is the clearest way to express the relationship:

    @Service
    public class ReportService {

        private final PricingPolicy pricingPolicy;

        public ReportService(PricingPolicy pricingPolicy) {
            this.pricingPolicy = pricingPolicy;
        }
    }

Spring must resolve PricingPolicy before completing the creation of ReportService. The relationship is expressed directly in the constructor and is easier to trace than a reference hidden inside a SpEL string.

When you need to ensure another bean is initialized earlier for a specific lifecycle reason that dependency injection does not express, `@DependsOn` can be used:

    @Component
    @DependsOn("databaseInitializer")
    public class ImportService {
        // ...
    }

`@DependsOn` declares that the specified bean must be initialized before the current bean. For singletons, Spring also uses this relationship to determine the appropriate bean destruction order.

Do not use `@DependsOn` to hide a normal data dependency; inject dependencies via constructors or setters. `@DependsOn` also cannot resolve a design-level circular dependency.

If you merely happen to call `@beanName` in an expression, do not rely on that implicit initialization order to express an important lifecycle requirement. Declare dependency relationships explicitly in configuration.

## 7. How Do Lazy Beans and Scopes Affect Timing?

Non-lazy singleton beans are typically created during the ApplicationContext refresh completion phase. Beans marked as lazy may be created when first requested.

However, if an expression is evaluated during bean initialization and directly references a lazy bean:

    @Value("#{ @largeCatalog.defaultCategory }")
    private String defaultCategory;

then resolving `@largeCatalog` can become the first access and trigger creation of that bean. Do not assume that marking a bean lazy will defer bean creation if an expression already requests the bean during startup.

With prototype scope, each time BeanFactory resolves the bean it may create a new instance. With request/session scope, resolution depends on the corresponding scope being active. If an expression is evaluated outside an active request and accesses a request-scoped bean, resolution may fail.

If a bean is wrapped in a scoped proxy, the expression usually receives the container-managed proxy object; method calls through the proxy are forwarded to the target matching the scope. Do not unwrap the proxy if you need to preserve scope or AOP behaviors.

## 8. Circular Dependencies Caused by Expressions

A circular dependency can form when bean A needs bean B during initialization, and bean B needs bean A:

    @Component
    public class A {
        @Value("#{ @beanB.name }")
        private String name;
    }

    @Component
    public class BeanB {
        private final A a;

        public BeanB(A a) {
            this.a = a;
        }
    }

In the example, resolving `@beanB` while injecting A can trigger creating B; B's constructor in turn requires A. With a constructor cycle, Spring cannot finish creating either object first to satisfy the other and will report a circular dependency error.

Some circular dependencies based on setter/field injection may be handled by the early singleton reference mechanism in suitable configurations, but you should not rely on this capability. Proxies, BeanPostProcessors, and lifecycle changes can also make dependency cycles less predictable.

A better solution is to extract shared logic into a third bean, invert the dependency via an interface, or use an API called at runtime instead of reading the other bean during value injection. If deferred access is needed, consider `ObjectProvider` or an explicit lazy mechanism in Java; do not use SpEL to hide dependency cycles.

## 9. BeanPostProcessor and BeanFactoryPostProcessor Are Created Very Early

BeanFactoryPostProcessor and BeanPostProcessor are infrastructure components involved in preparing the BeanFactory or creating beans. Spring must create them early so they can process other beans.

Because `@Value` and `@Autowired` are also processed by a BeanPostProcessor, do not rely on these annotations to inject dependencies into a class that itself implements BeanPostProcessor or BeanFactoryPostProcessor. Those infrastructure classes should be configured via constructors or factory methods with appropriate dependencies, or use Environment/BeanFactory APIs directly when appropriate.

Avoid having a BeanFactoryPostProcessor call regular business services just to evaluate an expression. Doing so can initialize beans too early, before all required BeanPostProcessors have been registered. Beans created prematurely may not undergo all the post-processing that regular beans receive.

When declaring infrastructure beans with `@Bean`, follow the static factory method and registration order requirements specified by Spring for that processor type.

## 10. Runtime Expression Evaluation vs. Bean Initialization Time

Not all SpEL runs at startup. For example, method security:

    @PreAuthorize("hasAuthority('invoice:read')")
    public Invoice getInvoice(Long id) {
        return invoiceRepository.findById(id).orElseThrow();
    }

This expression is evaluated by Spring Security when a method call passes through the method-security interceptor. It is not evaluated once when the InvoiceService bean is initialized.

Similarly, with SpEL used directly in Java:

    Expression expression =
            parser.parseExpression("#order.total * 1.1");

    Object value = expression.getValue(context);

the evaluation time is when the application calls `getValue(context)`. A parsed Expression can be reused, but each `getValue` call still evaluates against the context and data at the time of the call.

Distinguish the common evaluation timings:

| Where Expression Is Used | Evaluation Time |
|---|---|
| Bean definition value | When the container resolves the value during bean creation/configuration |
| `@Value("#{...}")` | When Spring injects the value into a constructor, field, or setter |
| `@PreAuthorize` | When the method-security interceptor processes a method invocation |
| SpEL called from Java | When the application calls `getValue()` or the corresponding evaluation API |

## 11. Being Careful with Side-Effect Methods in Initialization Expressions

An expression can call a method on a bean:

    @Value("#{ @startupService.prepareDefaultRegion() }")
    private String region;

If this method only computes a pure value, calling it during initialization may be appropriate. But if the method writes to a database, sends a message, calls an API, or mutates shared state, injecting a field can inadvertently trigger external actions.

Common risks:

- The method may run while the container is creating a dependency chain.
- An initialization error may occur after the side effect has already completed.
- If the bean is recreated in another context or test, the action may repeat.
- The order of side effects may depend on which bean is resolved first.
- A circular dependency may appear if the method calls back into a bean currently initializing.

Keep expressions in bean definitions and `@Value` simple, primarily reading properties or computing values. Place business actions into service methods called at a clear point after the context is ready.

## 12. Debugging Initialization Order Errors

When an expression fails to resolve a bean or property during startup, pinpoint where the failure occurs:

1. Did the error happen when parsing the expression or when evaluating it?
2. Has the bean containing the expression already been instantiated?
3. Is the expression being resolved during constructor injection or field/setter injection?
4. Does the referenced bean exist, is it lazy, or does it have a special scope?
5. Is there a reverse dependency forming a circular dependency?
6. Was the required BeanPostProcessor registered before that bean was created?
7. Does the called method depend on state only ready after init callbacks?

Read the stack trace to identify which bean is being created and which bean is requested during that process. You can enable appropriate Spring bean factory logging to trace bean creation, while avoiding logging sensitive data or secret configuration values.

A test using `ApplicationContextRunner` or an appropriate context test can help reproduce bean creation order and test expressions right during refresh. For method-security expressions, test method invocations separately after the context has started.

## 13. Takeaways

SpEL is evaluated where Spring or the application needs the expression's value. Values in bean definitions and `@Value` are typically resolved during bean creation, before init callbacks; `@beanName` references can trigger creation of other beans and expose circular dependencies or initialization side effects. Method-security expressions are evaluated when the method is called, whereas SpEL used directly in Java is evaluated when calling `getValue()`. Express real dependencies via constructor/setter injection, use `@DependsOn` for special lifecycle ordering, keep initialization expressions simple, and avoid depending on infrastructure beans that are not ready yet.
