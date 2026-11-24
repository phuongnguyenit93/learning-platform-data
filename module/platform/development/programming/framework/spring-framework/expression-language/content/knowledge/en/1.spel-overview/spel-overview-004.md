# Where Spring Uses SpEL Across the Ecosystem

Spring Expression Language (SpEL) is the expression language that many Spring components use to read properties, access parameters, invoke methods, compute values, or decide behavior at a specific point in the application lifecycle. Therefore, looking across the entire Spring ecosystem, SpEL appears in many places: bean configuration, event handling conditions, caching, authorization, data queries, batch jobs, and message flows.

The key point is that **each integration point provides its own evaluation context**. The same expression may be valid in one annotation but not have the same variables or root object in another annotation. Treat SpEL as part of the API published by each module, rather than assuming every Spring configuration string is interpreted as SpEL.

## 1. Recognizing Syntax and Context

Some components accept SpEL expressions inside **#{...}**. Some annotations accept the expression directly, such as **@Cacheable(key = "#isbn")** or **@PreAuthorize("hasRole('ADMIN')")**. The exact syntax depends on the integration point.

Common elements in expressions:

| Syntax | Meaning | Example |
| --- | --- | --- |
| **#name** | Named variable or parameter in the evaluation context | **#isbn**, **#root** |
| **@beanName** | Spring bean reference by name | **@permissionService.canRead(#order)** |
| **T(Type)** | Java type reference to access static members or create values per supported syntax | **T(java.lang.Math).max(3, 7)** |
| **.property** | Read a property/getter | **payload.total** |
| **[key]** | Access a map or collection element | **headers['tenantId']** |
| **method(...)** | Invoke a method permitted in the evaluation context | **#name.toUpperCase()** |

Two forms that often appear side by side must be distinguished:

- **${app.currency}** is a **property placeholder**: retrieves a configuration value from **Environment** or property sources.
- **#{...}** is a **SpEL expression**: evaluates an expression in the context provided by the Spring component.

For example:

~~~java
@Value("${app.currency:VND}")
private String currency;             // placeholder

@Value("#{systemProperties['user.country']}")
private String country;              // SpEL
~~~

Do not assume that every value in **application.properties** or **application.yml** automatically runs through SpEL. Only integration points with expression support evaluate expressions. Some annotations allow combining placeholders with SpEL; check the documentation for the exact annotation and version in use.

## 2. Common Integration Points

### 2.1. Spring Framework Core Container — Injecting Values and Referencing Beans

**@Value** allows injecting values from property placeholders or SpEL expressions. SpEL is useful when a value needs to be retrieved from a system property, a property of another bean, or a simple calculation.

~~~java
@Component
class RuntimeSettings {

    @Value("#{systemProperties['user.country']}")
    private String country;

    @Value("#{pricingRules.defaultTaxRate}")
    private BigDecimal taxRate;
}
~~~

In the example, **systemProperties** is data available in the context; **pricingRules** is a bean referenced by name. For ordinary configuration values, prefer placeholders such as **${app.tax-rate}** because the intent is clear and easy to manage across environments. Use SpEL when expression evaluation is genuinely needed.

### 2.2. Spring Application Events — Filtering Events with Conditions

**@EventListener** has a **condition** attribute that accepts SpEL. The listener is invoked only when the expression returns **true**.

~~~java
@Component
class OrderEventListener {

    @EventListener(condition = "#root.args[0].total >= 1000000")
    public void handleLargeOrder(OrderCreatedEvent event) {
        // handle orders with a total of 1,000,000 or more
    }
}
~~~

The event listener context provides the event and method arguments. Arguments can be accessed via **#root.args**, or by parameter name when that name is discovered by Spring. Using **#root.args[0]** makes it explicit that the expression reads the first argument.

This fits short filtering conditions tied directly to the event. If the rule needs to query data, has multiple branches, or involves complex business logic, move the decision into a bean/service and call it from the expression.

### 2.3. Spring Cache — Generating Cache Keys and Cache Decisions

The **@Cacheable**, **@CachePut**, and **@CacheEvict** annotations support SpEL for attributes such as **key**, **condition**, and **unless**.

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#isbn.rawNumber",
    condition = "#isbn != null",
    unless = "#result == null"
)
public Book findBook(ISBN isbn) {
    // load data
}
~~~

- **key**: determines the cache key from parameters or call metadata.
- **condition**: evaluated before the method executes; **false** means bypassing the cache for that call.
- **unless**: evaluated after a result is obtained; **true** prevents the result from being placed into the cache.
- **#result**: references the return value in expressions that support results.

The cache expression also has a root object containing method metadata, such as method, target, and arguments. Use **key** to produce stable, meaningful keys; avoid putting large objects or continuously changing values into the key if doing so reduces cache effectiveness.

### 2.4. Spring Security — Method-Level Authorization

Method Security uses SpEL to express access permissions based on authorities, principal, authentication, method parameters, or the returned object. Method security must be enabled, for example with **@EnableMethodSecurity**.

~~~java
@Service
class InvoiceService {

    @PreAuthorize(
        "hasAuthority('invoice:read') and " +
        "#tenantId == authentication.principal.tenantId"
    )
    public Invoice findInvoice(String tenantId, long invoiceId) {
        // ...
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Invoice readOwnedInvoice(long invoiceId) {
        // ...
    }
}
~~~

- **@PreAuthorize**: checked before invoking the method; commonly used for access conditions based on permissions and parameters.
- **@PostAuthorize**: checked after obtaining the result; can be used to verify that the user owns the returned object.
- **authentication**, **principal**, **hasAuthority(...)**, and **hasRole(...)** are components placed into the security expression context by Spring Security.

Parameter names such as **#tenantId** must be discovered properly by Spring. Depending on compilation and configuration, you may need to enable saving parameter names with **-parameters** or use a supporting annotation such as **@P**.

Do not place a post-condition **@PostAuthorize** check on a data-writing method if the write has already occurred before the permission is checked. For complex authorization logic, place the policy in a dedicated bean and call that bean from the expression. Keep expressions short so they are easy to read, test, and review for security.

### 2.5. Spring Data JPA — Expressions in @Query

Spring Data JPA supports a limited set of expressions in queries declared with **@Query**. One useful case is **#{#entityName}**, which represents the entity name associated with the repository domain type.

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Query("""
        select u
        from #{#entityName} u
        where u.lastname = ?1
        """)
    List<User> findByLastname(String lastname);
}
~~~

This approach is useful when writing generic repositories or when wanting to query by the entity name declared in the mapping. If the entity name changes, the query does not need to hard-code the old name.

Spring Data also supports value expressions for query parameters, such as **:#{#filter.status}** when a method accepts a **filter** parameter. Use the exact variables and syntax supported by the specific Spring Data module; do not assume the JPA evaluation context is identical to the context of Spring Security or Spring Integration.

### 2.6. Spring Batch — Late Binding for Job and Step

Batch jobs often receive parameters at runtime, such as an input file name, processing date, or values in **ExecutionContext**. Spring Batch uses SpEL to late-bind these values into beans with **step** or **job** scope.

~~~java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            // configure mapping and remaining properties
            .build();
}
~~~

Common data sources:

- **jobParameters**: parameters passed when launching the job.
- **jobExecutionContext**: data in the job's execution context.
- **stepExecutionContext**: data in the step's execution context.

Late binding only works properly when the bean is declared with the appropriate scope, typically **@StepScope** or **@JobScope**. A bean that needs to read step parameters should not be instantiated as a regular singleton before the step starts, because runtime data is not ready yet at that time.

### 2.7. Spring Integration — Operating on Messages

Spring Integration uses SpEL extensively to configure routers, filters, transformers, service activators, and many other endpoints. In most cases, the root object is **Message**; expressions can read **payload**, **headers**, and invoke beans in the application context.

For example, a filter that only lets messages with a total greater than 1,000 pass through:

~~~xml
<int:filter
    input-channel="orders"
    expression="payload.total > 1000" />
~~~

You can read headers or invoke beans:

~~~text
headers['tenantId']
@orderPolicy.canProcess(payload)
~~~

**payload** is the main content of the message; **headers** is key/value metadata. Some endpoints add their own variables, such as request parameters or path variables. Therefore, check the context provided by the specific endpoint before using a variable.

### 2.8. Spring AMQP — Configuring Listeners and Routing Replies

Spring AMQP allows using placeholders and SpEL in attributes of **@RabbitListener**, for example a list of queues retrieved from configuration:

~~~java
@RabbitListener(
    queues = "#{'${app.orders.queues}'.split(',')}"
)
public void processOrder(Order order) {
    // ...
}
~~~

With **@SendTo**, Spring AMQP supports two different evaluation times:

- **#{...}**: the expression is evaluated once when initializing the listener.
- **!{...}**: the expression is evaluated at runtime for each message; the context has **request**, **source**, and **result**.

For example, routing replies based on the processing result:

~~~java
@RabbitListener(queues = "orders")
@SendTo("!{'reply.' + result.region}")
public OrderReply process(Order order) {
    return handle(order);
}
~~~

Distinguish these two delimiter forms when configuring dynamic replies. **#{...}** uses the initialization-time context, whereas **!{...}** uses the request/reply data of the current processing call.

### 2.9. Spring Retry — Deciding Retries Based on Exceptions

Spring Retry provides attributes that accept expressions, such as **maxAttemptsExpression** and **exceptionExpression**. **exceptionExpression** is evaluated after the retry policy permits a retry and can use the last exception as the root object.

~~~java
@Retryable(
    exceptionExpression = "@retryPolicy.shouldRetry(#root)"
)
public void sendNotification() {
    // send notification
}
~~~

In the example, **#root** is the exception being examined and **retryPolicy** is the bean holding the retry decision. This approach is useful when the policy depends on the error type or exception content. Keep the policy centralized in a bean for easy testing and to avoid stuffing logic into annotations.

## 3. Comparing Evaluation Contexts by Module

| Integration Point | Commonly Accessed Data | Primary Purpose |
| --- | --- | --- |
| **@Value / Core Container** | system properties, beans, properties, and configuration values | inject values |
| **@EventListener** | event, **#root.args**, listener parameters | filter events |
| **Spring Cache** | parameters, method metadata, **#result** | generate keys and cache conditions |
| **Spring Security** | **authentication**, **principal**, authorities, parameters, **returnObject** | authorization |
| **Spring Data JPA** | **#entityName**, query parameters | build reusable queries |
| **Spring Batch** | **jobParameters**, **jobExecutionContext**, **stepExecutionContext** | late binding |
| **Spring Integration** | **payload**, **headers**, beans | route and transform messages |
| **Spring AMQP** | initialization context or **request** / **source** / **result** | configure listeners and replies |
| **Spring Retry** | exception and policy beans | retry decisions |

This table is a directional map, not a shared evaluation context. A variable such as **#result** has meaning in cache or AMQP reply contexts according to each module's rules; it cannot be carried over verbatim to **@EventListener**.

## 4. How to Choose Where to Use SpEL

1. **Use placeholders for simple configuration.** If you only need **app.timeout** or **app.region**, **${...}** is easy to understand and fits environment-based configuration.
2. **Use SpEL at documented integration points.** Only write expressions in attributes that the module confirms support SpEL.
3. **Identify context data before writing.** Check the root object, available variables, how parameters are accessed, and when the expression is evaluated.
4. **Keep expressions short.** A simple condition, cache key, or property access is usually easier to maintain than a multi-branch string.
5. **Put complex business logic into beans.** You can call **@policyService.isAllowed(...)** from SpEL, and then test the service like regular Java logic.
6. **Avoid side effects.** Expressions are for reading and deciding; do not rely on them to mutate system state.
7. **Do not evaluate untrusted expressions with a broadly privileged context.** SpEL can access properties and invoke methods depending on the evaluation context; restrict access permissions when building features that allow users to enter expressions.
8. **Test at the integration point.** Standalone parser tests do not prove that the module provides the right variables, the right root object, or the right evaluation timing.

## 5. Quick Takeaways

- **@Value**: inject values; distinguish **${...}** from **#{...}**.
- **@EventListener(condition = ...)**: filter events before invoking the listener.
- **@Cacheable**: **key**, **condition**, and **unless** serve cache decisions at different times.
- **@PreAuthorize** / **@PostAuthorize**: authorize before the call or after obtaining the result.
- Spring Data JPA: **#{#entityName}** helps reuse queries by domain type.
- Spring Batch: **jobParameters** and execution contexts are late-bound in beans with appropriate scope.
- Spring Integration: usually starts from **payload** and **headers**.
- Spring AMQP: distinguish **#{...}** at initialization from **!{...}** at message processing time.
- Each module has its own context and rules; always consult documentation for the dependency version in use.

## 6. Official References

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — @Value Annotation](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Data JPA — Query Methods and Expressions](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Batch — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Integration — SpEL](https://docs.spring.io/spring-integration/reference/spel.html)
- [Spring AMQP — Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [Spring AMQP — Reply Management](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/reply.html)
- [Spring Retry — @Retryable API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
