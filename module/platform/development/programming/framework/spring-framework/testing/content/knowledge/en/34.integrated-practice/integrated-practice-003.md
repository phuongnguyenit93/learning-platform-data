# Testing Bean Configuration and a Proxy-Intercepted Behavior

A Spring application can start up successfully yet still pick the wrong bean, miss a profile-specific configuration, or fail to apply a proxy-activated mechanism. Therefore, testing a class by calling `new` directly is not enough to prove the application works properly when managed by Spring.

An integration test at the right level needs to verify two related but distinct things:

1. **Bean configuration:** Spring creates the right beans, injects the right dependencies, selects the right implementation, and applies the right environment configuration.
2. **Behavior through the proxy:** calls pass through the Spring-created proxy so interceptors such as transaction, cache, retry, security, or async are actually applied.

This lesson uses `@Transactional` as the representative behavior. The test loads real Spring configuration, retrieves the service from `ApplicationContext`, verifies that the service is proxied, and proves that a database write is rolled back when the method throws a runtime exception. The same approach applies to other proxy-based behaviors.

## 1. Distinguishing Plain Object Testing from Spring Bean Testing

Suppose we have a service:

```java
class OrderService {

    private final OrderRepository orderRepository;

    OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void createOrder(Order order) {
        orderRepository.save(order);
    }
}
```

A unit test can instantiate the service directly and pass a mock repository:

```java
OrderRepository repository = mock(OrderRepository.class);
OrderService service = new OrderService(repository);

service.createOrder(order);

verify(repository).save(order);
```

This test is useful for verifying the logic that calls the repository. However, an object created with `new` does not go through the Spring container, so `@Transactional` does not automatically start a transaction. Similarly, `@Cacheable`, `@Async`, `@Retryable`, or `@PreAuthorize` do not work automatically just because the annotation is present on the method.

When you need to verify bean wiring and Spring-applied behavior, you must retrieve the bean from the context:

```java
@Autowired
OrderService orderService;
```

Spring creates the target object, registers the bean, and can wrap it in a proxy. The test invokes the injected bean to go through the same mechanism that the application uses.

## 2. Loading the Right Spring Configuration in Tests

Spring Test provides several ways to build an application context. Choose the one suited to the scope you need to test:

| Context Setup Approach | Scope | When to Use |
|---|---|---|
| `@SpringJUnitConfig(TestConfig.class)` | Spring TestContext with specified Java/XML configuration | Testing a well-scoped group of beans and infrastructure. |
| `@ContextConfiguration(classes = ...)` | Registers configuration or initializers for the context | When fine-grained control over context configuration is needed. |
| `@Import(TestConfig.class)` | Adds configuration to an existing test context | Adding supporting beans or replacing part of the configuration. |
| `@SpringBootTest` | Loads the Spring Boot application context | Testing auto-configuration, component scanning, profiles, and full-application wiring. |
| `ApplicationContextRunner` | Creates a small context per run | Testing auto-configuration and bean creation conditions quickly and independently. |

### Using `@SpringJUnitConfig`

When the goal is to test a specific configuration, `@SpringJUnitConfig` keeps the test concise without booting the entire application:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderTestConfiguration.class)
class OrderConfigurationTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void registersOrderService() {
        assertThat(applicationContext.getBean(OrderService.class))
                .isNotNull();
    }
}
```

`@SpringJUnitConfig` combines JUnit Jupiter support with Spring TestContext. The context is built according to the specified configuration and can be reused via the context cache if tests share the same configuration.

### Using `@SpringBootTest`

If what you need to verify depends on component scanning, auto-configuration, profiles, or application properties, load the real application context:

```java
@SpringBootTest
class ApplicationBeanConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void loadsRequiredApplicationBeans() {
        assertThat(context.getBean(OrderService.class)).isNotNull();
        assertThat(context.getBean(PlatformTransactionManager.class)).isNotNull();
    }
}
```

You do not need `@SpringBootTest` for every bean test. A full context may initialize many services and slow down the suite. If a small configuration is enough to prove the required wiring, using `@SpringJUnitConfig` makes the test scope easier to understand.

## 3. Verifying That Beans Are Registered and Injected Correctly

A context test should verify important configuration contracts, such as:

- Required beans are present.
- Only one bean matches the injected dependency type, or a bean is chosen via `@Primary`/`@Qualifier`.
- Beans are created from the right profile or properties.
- The right implementation is used in the test environment.
- Beans depend on the same infrastructure instance when that matters, e.g., repository and transaction manager sharing the same `DataSource`.

For example, suppose there are two implementations of `PaymentGateway`:

```java
interface PaymentGateway {
    String providerName();
}

class CardPaymentGateway implements PaymentGateway {
    @Override
    public String providerName() {
        return "card";
    }
}

class SandboxPaymentGateway implements PaymentGateway {
    @Override
    public String providerName() {
        return "sandbox";
    }
}
```

Configuration selecting a default bean and a qualified bean:

```java
@Configuration
class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("sandbox")
    PaymentGateway sandboxPaymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

A test can verify both the default selection and the qualified selection:

```java
@SpringJUnitConfig(PaymentConfiguration.class)
class PaymentConfigurationTest {

    @Autowired
    PaymentGateway defaultGateway;

    @Autowired
    @Qualifier("sandbox")
    PaymentGateway sandboxGateway;

    @Test
    void selectsTheExpectedPaymentImplementations() {
        assertThat(defaultGateway.providerName()).isEqualTo("card");
        assertThat(sandboxGateway.providerName()).isEqualTo("sandbox");
    }
}
```

This test verifies Spring's bean selection rules, not just that the two classes can be instantiated independently.

### Testing Profiles and Conditional Properties

When a bean depends on a profile:

```java
@Configuration
class NotificationConfiguration {

    @Bean
    @Profile("test")
    NotificationClient testNotificationClient() {
        return new StubNotificationClient();
    }
}
```

A test can activate the profile using `@ActiveProfiles("test")` and then verify the registered implementation. For Spring Boot auto-configuration using `@ConditionalOnProperty`, `ApplicationContextRunner` makes it easy to test both property-enabled and property-disabled cases:

```java
new ApplicationContextRunner()
        .withUserConfiguration(AuditAutoConfiguration.class)
        .withPropertyValues("app.audit.enabled=true")
        .run(context -> assertThat(context).hasSingleBean(AuditPublisher.class));

new ApplicationContextRunner()
        .withUserConfiguration(AuditAutoConfiguration.class)
        .withPropertyValues("app.audit.enabled=false")
        .run(context -> assertThat(context).doesNotHaveBean(AuditPublisher.class));
```

`ApplicationContextRunner` fits auto-configuration tests well because each `run` creates a small context with its own properties. It verifies bean registration conditions without booting the entire application.

## 4. How Do Spring Proxies Work?

Spring AOP typically applies cross-cutting behaviors by wrapping a bean in a proxy. Callers invoke the proxy; the proxy runs the appropriate interceptors/advice and then delegates the call to the target object.

```text
Caller
  |
  v
Spring-managed bean reference
  |
  v
Proxy
  |
  +--> Transaction interceptor
  |       - begin transaction
  |       - invoke target method
  |       - commit or rollback
  |
  v
Target object
  |
  v
Repository / database
```

With `@Transactional`, the transaction interceptor obtains the appropriate `PlatformTransactionManager`, begins or joins a transaction, invokes the method on the target, and then commits or rolls back based on the outcome.

Proxies can be created in two common ways:

- **JDK dynamic proxy:** proxy based on the interfaces implemented by the bean. Callers typically inject via the interface.
- **Class-based proxy (CGLIB):** generates a subclass of the target class to intercept method calls.

With default transaction configuration, Spring typically uses a JDK proxy when the target implements an interface and a class-based proxy when no suitable interface exists. Options such as `proxyTargetClass` can change that choice. Spring Boot may also set its own default proxy configuration.

What matters for testing is retrieving the bean from the context and invoking the method through the injected reference. Creating the target manually with `new`, calling an internal method directly, or unwrapping the target object behind the proxy will bypass the interceptor.

## 5. Choosing a Proxy Behavior to Test: Transaction Rollback

`@Transactional` is a good example because its effect can be observed in the database. If the method performs a write statement and then throws a runtime exception, the transaction interceptor rolls back the transaction by default. The test verifies that the record does not exist after the failed call.

Behavior to prove:

```text
Test calls Spring-managed OrderService proxy
                 |
                 v
        Transaction interceptor
                 |
          BEGIN transaction
                 |
                 v
          INSERT order row
                 |
                 v
          Runtime exception
                 |
                 v
          ROLLBACK transaction
                 |
                 v
       Query from test: no row
```

For this test to be meaningful, the test method itself must not open a transaction around the service call. If the test already has an outer transaction, the service's transaction may join that transaction and the data will not have been rolled back at the moment the assertion runs.

## 6. Creating a Test Configuration with a Real DataSource and Transaction Manager

The following example uses an H2 embedded database and `JdbcTemplate`. H2 allows testing transaction behavior without installing an external database server.

Test dependencies require Spring Test, Spring JDBC, H2, and JUnit Jupiter. When using Spring Boot dependency management, let the BOM manage compatible versions:

```groovy
testImplementation 'org.springframework:spring-test'
testImplementation 'org.springframework:spring-jdbc'
testImplementation 'com.h2database:h2'
testImplementation 'org.junit.jupiter:junit-jupiter'
```

Spring configuration registering DataSource, JdbcTemplate, transaction manager, and service:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
class TransactionalTestConfiguration {

    @Bean
    EmbeddedDatabase dataSource() {
        return new EmbeddedDatabaseBuilder()
                .setType(EmbeddedDatabaseType.H2)
                .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    InitializingBean createSchema(JdbcTemplate jdbcTemplate) {
        return () -> jdbcTemplate.execute("""
                create table orders (
                    id varchar(100) primary key
                )
                """);
    }

    @Bean
    OrderService orderService(JdbcTemplate jdbcTemplate) {
        return new OrderService(jdbcTemplate);
    }
}
```

`@EnableTransactionManagement` registers the infrastructure that processes transaction annotations. `DataSourceTransactionManager` manages JDBC transactions on the same DataSource injected into `JdbcTemplate`. Both the service and the test use the same database in the context.

`EmbeddedDatabase` is a `DataSource` with a shutdown lifecycle. Because it is registered as a bean, Spring shuts it down when the context closes.

## 7. Service with One Succeeding Method and One Intentionally Failing Method

The service below has two public methods, both marked `@Transactional`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

class OrderService {

    private final JdbcTemplate jdbcTemplate;

    OrderService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void create(String orderId) {
        jdbcTemplate.update(
                "insert into orders (id) values (?)",
                orderId);
    }

    @Transactional
    public void createThenFail(String orderId) {
        jdbcTemplate.update(
                "insert into orders (id) values (?)",
                orderId);

        throw new IllegalStateException("Simulated failure after insert");
    }
}
```

`createThenFail` writes data before throwing `IllegalStateException`. By default, Spring rolls back the transaction when a method throws an unchecked exception (`RuntimeException` or `Error`). Therefore, the insert statement must be rolled back.

If a method throws a checked exception, Spring does not roll back by default for that exception alone. When business requirements call for rollback on a checked exception, declare `rollbackFor` or an appropriate rollback rule and write a test verifying that policy.

## 8. Retrieving the Bean from the Context and Calling Through the Proxy

The test uses `@SpringJUnitConfig` to build the context and inject the service and JdbcTemplate. The test methods are not annotated with `@Transactional`:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TransactionalTestConfiguration.class)
class OrderServiceProxyTest {

    @Autowired
    OrderService orderService;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @BeforeEach
    void cleanDatabase() {
        jdbcTemplate.update("delete from orders");
    }

    @Test
    void injectsAProxiedOrderService() {
        assertThat(AopUtils.isAopProxy(orderService)).isTrue();
        assertThat(AopUtils.getTargetClass(orderService))
                .isEqualTo(OrderService.class);
    }

    @Test
    void commitsWhenTransactionalMethodReturnsNormally() {
        orderService.create("order-100");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class,
                "order-100");

        assertThat(count).isEqualTo(1);
    }

    @Test
    void rollsBackInsertWhenTransactionalMethodThrowsRuntimeException() {
        assertThatThrownBy(() -> orderService.createThenFail("order-200"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Simulated failure after insert");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class,
                "order-200");

        assertThat(count).isZero();
    }
}
```

The test above verifies three things:

1. The injected bean is an AOP proxy.
2. A successful call commits the data.
3. A call throwing a runtime exception rolls back the data written in the same transaction.

The `AopUtils.isAopProxy(...)` assertion helps verify that a proxy exists, but the database outcome is the stronger evidence. A proxy could exist without applying the desired interceptor if misconfigured; checking the transaction effect proves actual runtime behavior.

## 9. Why Should the Test Method Not Have `@Transactional` in the Rollback Example?

Spring Test can open a transaction for the test method itself when `@Transactional` is placed on the class or method. This transaction is typically rolled back after the test finishes.

If the service uses the default `REQUIRED` propagation, the transaction opened by the service joins the test's existing transaction. When `createThenFail` throws an exception, the transaction may be marked rollback-only, yet the test is still inside the outer transaction. A query executed immediately after catching the exception may still see the unrolled-back row until the test transaction finishes.

Consequently, the test can produce misleading results if it checks the database before the test transaction rolls back. In this test, to let the service own its transaction and inspect the database state after the proxy finishes the call, do not annotate the test method with `@Transactional`.

If your test suite has a default transaction policy on a base class, move the proxy transaction test to a class that does not participate in test-managed transactions, or explicitly configure how transactions end before assertions.

## 10. Bean Configuration and Proxy Behavior Are Two Distinct Layers of Evidence

A test can confirm a bean exists without proving its annotations work. Conversely, a rollback test can prove transaction behavior without necessarily verifying all of the application's bean selection.

Separate assertions by goal:

| What Needs to Be Proven | Appropriate Evidence |
|---|---|
| Configuration class is loaded | Context starts with the specified configuration. |
| Bean exists | `context.getBean(...)` or `hasSingleBean(...)` assertion. |
| Right implementation is selected | Check bean by type, qualifier, profile, or property. |
| Dependencies are injected correctly | Invoke the real bean or verify the selected collaborator through behavior. |
| Bean is proxied | `AopUtils.isAopProxy(bean)` or check proxy type when needed. |
| Transaction actually works | Observe commit/rollback on a real resource or transaction state during the call. |
| Security/retry/cache/async actually works | Invoke through the bean proxy and verify the corresponding effect. |

Do not rely on checking `bean.getClass()` against a specific class name. Proxy class names can vary across JDK/CGLIB, Spring versions, and configuration. Use `AopUtils`, interface contracts, and observable behavior for more resilient assertions.

## 11. The Self-Invocation Pitfall: Internal Calls Bypass the Proxy

Proxy-based AOP only intercepts calls passing through the proxy. If a method on the target calls another method on `this`, the internal call does not go back through the proxy.

Example:

```java
@Service
class BillingService {

    public void processInvoice(String invoiceId) {
        saveInvoice(invoiceId);
    }

    @Transactional
    public void saveInvoice(String invoiceId) {
        // Write data.
    }
}
```

When a caller invokes `billingService.processInvoice(...)`, the internal `this.saveInvoice(...)` call inside the target does not pass through the proxy again. The transaction annotation on `saveInvoice` may not be applied as expected.

A usually better solution is to place the transaction boundary on the public method called from outside:

```java
@Transactional
public void processInvoice(String invoiceId) {
    saveInvoiceData(invoiceId);
}

private void saveInvoiceData(String invoiceId) {
    // Write data inside processInvoice's transaction.
}
```

Or extract the part that needs a transaction into a separate collaborator bean so the call goes through that bean's proxy. Avoid introducing self-injection or retrieving the proxy from `AopContext` in every class just to work around self-invocation; those approaches increase coupling and make call flows harder to follow.

A proxy test should call the exact public entry point that the application calls. Calling the annotated method directly on the target object fails to verify the proxy path.

## 12. Class and Method Constraints When Using Proxies

With a JDK dynamic proxy, calls normally must go through an interface exposed by the bean. Callers should inject the interface rather than attempting to cast to the implementation class.

With a class-based proxy (CGLIB):

- A `final` class cannot be subclassed to create a proxy.
- A `final` method cannot be overridden to intercept calls.
- A `private` method cannot be intercepted by a proxy subclass.
- Public methods are the most predictable choice for proxy-based annotations.

If a bean is not proxied as expected, check the proxy type, interfaces, class/method modifiers, and how the bean is created. An object instantiated manually, returned from a factory outside Spring, or unwrapped from its proxy can also bypass interception.

## 13. Which Other Proxy Behaviors Can This Approach Test?

`@Transactional` is just one example. The general principle is: load the real bean, invoke it through the reference from the context, and verify the effect produced by the interceptor.

| Behavior | What to Verify Through the Proxy |
|---|---|
| `@Cacheable` | Second call uses the cache for the expected key; backing collaborator is not called again on cache hit. |
| `@CacheEvict` | Cache entry is evicted at the configured time and for the configured key. |
| `@Async` | Work runs on a different executor or returns a `CompletableFuture` completing with the right result. |
| `@PreAuthorize` | Unauthorized principal is rejected before the target method executes business logic. |
| `@Retryable` | Call is retried the expected number of times and stops on success or exhausted retries. |
| Custom Spring AOP advice | Advice runs before/after target according to configured pointcut and order. |

For each type, concrete behavioral assertions are needed. Checking `AopUtils.isAopProxy(...)` alone does not prove cache hits, async dispatch, security denial, or retry policies are working properly.

### Short Example with `@Cacheable`

Suppose a service reads product prices and caches the result:

```java
@Service
class ProductPriceService {

    private final PriceRepository repository;

    ProductPriceService(PriceRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "prices", key = "#sku")
    public BigDecimal priceOf(String sku) {
        return repository.findPrice(sku);
    }
}
```

The test must load `@EnableCaching`, a cache manager, and the service bean from the context. Call the same key twice, verify the results match, and verify the repository is called only once. If the service is created with `new`, the cache interceptor will not run. The test must also clear the cache between tests so it does not reuse data from the cached context.

## 14. When to Use `@TestConfiguration`, `@Import`, and Bean Overrides?

In integration tests, you sometimes need to replace an external dependency with a stub or mock while keeping the real service and real proxy.

`@TestConfiguration` can add test-only beans:

```java
@TestConfiguration
class TestGatewayConfiguration {

    @Bean
    @Primary
    PaymentGateway testPaymentGateway() {
        return new StubPaymentGateway();
    }
}
```

Load the configuration using `@Import(TestGatewayConfiguration.class)` in the test. Be careful if the application already has a bean of the same type with another `@Primary`; verify which bean is actually selected.

With Spring Boot, you can use the mock bean mechanism appropriate for your Spring Boot version. Some older APIs like `@MockBean` are gradually being superseded by newer bean override mechanisms in newer Spring Framework/Boot versions. Regardless of the tool, the test must keep the bean under test (e.g., the transactional service) as a real Spring-managed bean, replacing only external collaborators intentionally.

Do not mock the very bean whose proxy the test wants to verify. If `OrderService` is replaced with a mock, the test no longer proves `@Transactional` on the real implementation.

## 15. Verifying Transactions via the Transaction Manager or via the Database?

There are two common approaches:

**Observing transaction state:** inside a collaborator called by the service, check `TransactionSynchronizationManager.isActualTransactionActive()` or record transaction state. This is useful when confirming the call is inside a transaction, but it does not prove data actually rolls back on the resource.

**Observing database outcome:** write data and then throw an exception; after the proxy completes the call, query the database again and verify the data does not exist. This tests the transaction interceptor, transaction manager, DataSource, and how the repository participates in the transaction.

For critical transactional behavior, checking the database usually provides stronger evidence. Use the real transaction manager for the active persistence technology, such as `DataSourceTransactionManager` for JDBC or `JpaTransactionManager` for JPA. Do not substitute a mock transaction manager if the goal is to prove resource commit/rollback.

## 16. Common Mistakes When Testing Beans and Proxies

### Instantiating the Service with `new`

A manually instantiated object is not wrapped in a proxy by Spring. Annotations remain on the class, yet interceptors are never invoked. Inject the bean from the context.

### Only Asserting That the Bean Exists

A bean may exist yet be the wrong implementation or lack a proxy. Check qualifiers/profiles/properties and observable behavior.

### Only Asserting That a Proxy Exists

A proxy may be created while its interceptor or transaction manager is misconfigured. Verify commit/rollback results or annotation effects.

### Test Calling an Internal Method

Self-invocation bypasses the proxy. Call the public entry point through the injected bean or extract the collaborator into a separate bean.

### Test Method Also Marked `@Transactional`

The service's transaction may join the test's outer transaction, causing assertions to check for rollback before rollback actually occurs. Use a test without an outer transaction for rollback examples, or end the transaction explicitly before assertions.

### Throwing a Checked Exception While Expecting Default Rollback

Spring rolls back by default on unchecked exceptions and `Error`. If rollback on a checked exception is required, configure `rollbackFor` and verify it with a test.

### Using Final/Private Methods for Proxy-Based Annotations

A proxy subclass cannot override final classes/methods; private methods are not intercepted. Place annotations on methods compatible with the proxy model and invoke them from outside the bean.

### Using the Wrong Transaction Manager or DataSource

If the repository and transaction manager do not use the same resource, the transaction may not wrap the operation under test. Verify wiring and qualifiers for both.

### Cleaning Up the Database at the Wrong Time

If tests run in parallel or share a context, data can affect other tests. Use unique IDs, per-fixture cleanup, or isolated databases; do not rely on test execution order.

## 17. Organizing Tests by Scope

You do not need a single huge test to verify all Spring configuration. You can split them into groups:

| Test Group | Goal | Suitable Configuration |
|---|---|---|
| Bean configuration test | Bean is present; qualifier/profile/condition picks right implementation | `@SpringJUnitConfig` or `ApplicationContextRunner`. |
| Proxy behavior test | Interceptor actually applies when invoking the bean | Real Spring context and observable collaborator/resource. |
| Persistence integration test | Transaction and repository work together on a database | Embedded DB or Testcontainers with a real transaction manager. |
| Application context test | Component scanning, auto-configuration, and application profiles | `@SpringBootTest` with required properties/profiles. |

Separating tests makes failures easier to pinpoint. If bean selection is wrong, the configuration test highlights the problem. If the proxy exists but rollback fails, the proxy behavior test fails at the database assertion.

## 18. Checklist for Bean Configuration and Proxy Tests

- [ ] Test loads the exact Spring configuration to be verified.
- [ ] Bean is retrieved from `ApplicationContext` or injected by Spring, not manually created with `new` for the target needing a proxy.
- [ ] Bean type, qualifier, primary, profile, or properties are verified against the configuration contract.
- [ ] Related infrastructure is properly registered, such as transaction manager and DataSource.
- [ ] Proxy behavior is invoked from an entry point outside the proxy.
- [ ] Assertions verify the actual effect of the interceptor, not just the annotation or proxy class.
- [ ] For transactions, the test observes commit/rollback on an appropriate resource.
- [ ] Test does not inadvertently open an outer transaction that distorts assertion timing.
- [ ] Self-invocation, method visibility, and `final` modifiers have been checked.
- [ ] Mocks replace only collaborators outside the test target.
- [ ] Test cleans up data and caches so state does not leak across runs.

Testing bean configuration proves Spring builds the right dependency graph; testing proxies proves calls actually pass through the interceptors the application relies on. Combining a context test with an observable behavior such as transaction rollback provides evidence that the bean is not only registered properly, but also works properly under Spring's runtime mechanism.
