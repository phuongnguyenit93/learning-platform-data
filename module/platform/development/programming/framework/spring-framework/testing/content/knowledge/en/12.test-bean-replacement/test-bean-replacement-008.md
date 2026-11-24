# Singleton Scope, FactoryBean, and Version Differences

When replacing a bean in Spring tests, you need to understand which scope that bean uses and whether it is created directly or through a **FactoryBean**. These details determine whether the test can replace the bean, which object is actually replaced, and whether the test preserves the application's lifecycle behavior.

Starting in Spring Framework 6.2, Spring TestContext provides a dedicated bean overriding mechanism with **@TestBean**, **@MockitoBean**, and **@MockitoSpyBean**. This mechanism has its own rules for scopes and FactoryBean. In particular, the rule for non-singleton beans changed between the Framework 6.2 and 7.0 branches. If you follow documentation from a different version than the one running, tests may fail during context creation or accidentally turn a per-request dependency into a shared object.

This lesson explains singleton scope in Spring, how bean overrides handle other scopes, the difference between a FactoryBean and the object it produces, and important changes across Spring Framework and Spring Boot versions.

## 1. What Is Bean Overriding in Tests?

Bean overriding in tests is the act of replacing a bean in the ApplicationContext with another object intended for testing. The usual goal is to isolate an external dependency, simulate hard-to-reproduce errors, or observe interactions without calling real systems.

For example, OrderService depends on PaymentGateway:

~~~java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            PaymentGateway paymentGateway,
            OrderRepository orderRepository
    ) {
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public OrderResult placeOrder(OrderCommand command) {
        var payment = paymentGateway.charge(command.amount());

        if (!payment.approved()) {
            return OrderResult.rejected();
        }

        var order = orderRepository.save(
                new Order(command.customerId(), command.amount())
        );

        return OrderResult.created(order.getId());
    }
}
~~~

When testing a controller or the entire service layer, we may want to keep the real OrderService while replacing PaymentGateway with a Mockito mock:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void shouldCreateOrderWhenPaymentIsApproved() {
        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.approved());

        var result = orderService.placeOrder(
                new OrderCommand("customer-1", new BigDecimal("250000"))
        );

        assertEquals(OrderStatus.CREATED, result.status());
        verify(paymentGateway).charge(new BigDecimal("250000"));
    }
}
~~~

**@MockitoBean** instructs Spring TestContext to create a Mockito mock and register it in the context following bean override rules. Other beans injecting PaymentGateway receive that mock.

Spring Framework 6.2 introduced three primary annotations:

| Annotation | How It Works | Purpose |
|---|---|---|
| @TestBean | Replaces a bean with an object supplied by a test static factory method | Use a fake or custom implementation |
| @MockitoBean | Replaces a bean with a Mockito mock | Control responses and verify calls |
| @MockitoSpyBean | Wraps a real instance with a Mockito spy | Keep most real behavior and observe interactions |

All three annotations use Spring TestContext's bean override infrastructure. Thus, the rules for scope, FactoryBean, and bean lookup apply at the infrastructure level, not only to Mockito.

## 2. What Does Singleton Scope Mean in Spring?

Singleton is the default scope for a Spring bean. For a given bean definition in a Spring IoC container, Spring manages a single shared instance. Components injecting that same bean receive the same instance within the corresponding context.

Example:

~~~java
@Component
public class PaymentAuditService {
    // Singleton bean by default.
}
~~~

Equivalent to declaring the scope explicitly:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
public class PaymentAuditService {
}
~~~

Spring's singleton is scoped **per container and per bean definition**. It is not a JVM-wide singleton like the GoF design pattern. Two separate ApplicationContexts can hold two separate instances of the same class.

Common scopes:

| Scope | Instance Lifecycle |
|---|---|
| singleton | One instance per bean definition in a container |
| prototype | Creates a new instance each time the container requests the bean |
| request | One instance per HTTP request |
| session | One instance per HTTP session |
| application | One instance per ServletContext |
| websocket | One instance per WebSocket session |
| Custom scope | Follows the rules of the registered Scope |

Web scopes only work inside a web-aware ApplicationContext. Prototype can be used in ordinary contexts.

Example of a prototype bean:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class RequestToken {

    private final String value = UUID.randomUUID().toString();

    public String value() {
        return value;
    }
}
~~~

Every time `getBean(RequestToken.class)` is called, Spring creates a new instance. If a prototype is injected directly into a singleton, the dependency is resolved once when the singleton is created; to obtain a fresh instance on each execution, ObjectProvider, Provider, or method injection is usually needed.

A key point when replacing beans in tests: a mock is usually a single object created for the test context. If the original bean had a per-request or prototype lifecycle, replacing it with a singleton mock can alter the meaning of the test.

## 3. Bean Override Strategies

Spring's bean override infrastructure has three strategies:

| Strategy | Behavior | Common Annotation |
|---|---|---|
| REPLACE | Replaces an existing bean; fails if no bean is found | @TestBean with enforceOverride enabled |
| REPLACE_OR_CREATE | Replaces the bean if present; creates a new bean if absent | Default for @TestBean and @MockitoBean |
| WRAP | Takes an existing instance and wraps it | @MockitoSpyBean |

### 3.1. @MockitoBean: Replacing with a Mock

~~~java
@SpringBootTest
class PaymentServiceTest {

    @Autowired
    private PaymentService paymentService;

    @MockitoBean
    private PaymentGateway paymentGateway;
}
~~~

By default, @MockitoBean uses REPLACE_OR_CREATE. If no matching bean exists, Spring can create a new mock and register it in the context.

This is useful when a test needs to supply a dependency that a slice configuration does not load. However, if the goal is to verify that the application actually has the production bean, creating a mock automatically when the original bean is missing can hide configuration errors.

Use enforceOverride = true to require the bean to exist:

~~~java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
~~~

In that case, Spring uses the REPLACE strategy. If no matching bean is found, context creation fails. This is the right choice when you want to ensure the test replaces an actual dependency configured in the application.

### 3.2. @MockitoSpyBean: Wrapping a Real Bean

~~~java
@SpringBootTest
class PricingServiceTest {

    @MockitoSpyBean
    private PricingService pricingService;

    @Test
    void shouldCalculatePriceUsingRealImplementation() {
        var result = pricingService.calculate(sampleOrder());

        assertTrue(result.total().signum() > 0);
        verify(pricingService).calculate(any());
    }
}
~~~

@MockitoSpyBean uses the WRAP strategy. Spring obtains the real instance and creates a spy around it. The test can execute real logic while stubbing or verifying selected methods.

This strategy requires exactly one matching bean. If multiple beans of the same type exist and the target bean cannot be disambiguated, the test fails. Use @Qualifier or a bean name to identify the candidate clearly.

When stubbing a spy, consider `doReturn(...).when(spy)...` or `doThrow(...).when(spy)...` if the real call could trigger side effects while setting up the stub.

### 3.3. @TestBean: Replacing with a Test-Provided Fake

@TestBean uses a static factory method to create the replacement object:

~~~java
@SpringBootTest
class OrderServiceTest {

    @TestBean
    private PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

By convention, Spring looks for a factory method based on the field name. You can specify a different method name via the methodName attribute. The factory method must be static, take no parameters, and return a type compatible with the bean being replaced.

@TestBean also supports enforceOverride. When you need to verify that the production bean exists, enable this attribute so the test fails if the target bean cannot be found.

## 4. Singleton Scope in Spring Framework 6.2

In the Spring Framework 6.2.x documentation, bean overriding only supports singleton-scoped beans. If a test attempts to replace a prototype bean or a bean with another scope, Spring throws an exception while preparing the ApplicationContext.

Example prototype bean:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TokenGenerator {

    public String generate() {
        return UUID.randomUUID().toString();
    }
}
~~~

The following test is invalid under Framework 6.2.x bean override rules:

~~~java
@SpringBootTest
class TokenGeneratorTest {

    @MockitoBean
    private TokenGenerator tokenGenerator;
}
~~~

The target bean is a prototype, so Spring Framework 6.2.x rejects the override. Switching @MockitoBean to @MockitoSpyBean or @TestBean does not bypass this shared restriction.

The reason relates to object lifecycle. Prototypes are designed to create a new instance on each request. A mock or replacement object managed as a single override instance in the context cannot preserve the prototype's fresh-instance contract under the 6.2 mechanism.

For request, session, or custom scopes, the same restriction applies: if the target bean is identified as non-singleton, the 6.2.x override infrastructure rejects the operation.

This does not mean Spring lacks support for those scopes in applications. It only describes the limitation of the test bean-replacement mechanism in this version.

## 5. Changes Starting in Spring Framework 7.0 for Non-Singleton Beans

The bean overriding documentation for Spring Framework 7.0 describes new behavior for non-singleton beans: when replacing such a bean, Spring registers the override instance as a singleton and converts the corresponding bean definition's scope to singleton.

This differs from the 6.2.x rule:

| Version | When Overriding a Prototype or Scoped Bean |
|---|---|
| Spring Framework 6.2.x | Rejects non-singleton override and throws an exception |
| Spring Framework 7.0 | Replaces with a singleton override instance; bean definition is converted to singleton |

Example with prototype:

~~~java
@SpringBootTest
class TokenGeneratorTest {

    @MockitoBean(enforceOverride = true)
    private TokenGenerator tokenGenerator;

    @Test
    void shouldReturnStubbedToken() {
        when(tokenGenerator.generate()).thenReturn("test-token");

        assertEquals("test-token", tokenGenerator.generate());
    }
}
~~~

With Framework 7.0, a prototype bean can be replaced by a singleton mock. The test can run, yet the mock is no longer created anew on each bean lookup like the original prototype.

This change affects test semantics. If production code depends on receiving an independent object on each prototype lookup, a singleton mock does not simulate that behavior.

Similarly, replacing a request-scoped bean with a singleton mock can cause multiple requests in the same test context to observe the same object. Tests might miss bugs caused by state leaking across requests.

With @MockitoSpyBean, Framework 7.0 also converts a non-singleton bean definition to singleton when creating a spy for that bean. Note the special case of scoped proxies: @MockitoSpyBean does not support directly spying on a scoped proxy, such as a bean using `@Scope(proxyMode = ScopedProxyMode.TARGET_CLASS)`. That case can fail even in versions that support scope conversion.

### Example of the Risk of Changing Scope

Suppose a bean holds per-request state:

~~~java
@Component
@RequestScope
public class RequestContextData {

    private String correlationId;

    public void setCorrelationId(String correlationId) {
        this.correlationId = correlationId;
    }

    public String getCorrelationId() {
        return correlationId;
    }
}
~~~

In the real application, each HTTP request gets its own instance. If a test on Framework 7.0 replaces this bean with a singleton mock, two request executions can share that mock.

If the test only checks one request, the result may still look right. Yet the test does not prove that state is isolated across requests.

When you need to test true request lifecycle behavior, run the test with real request scope and issue two separate requests. Do not use a singleton mock as evidence of per-request isolation.

## 6. Why Turning Non-Singletons into Singletons Can Distort Test Meaning

Scope is part of a bean's contract. When a test alters scope, the following properties can change:

- Whether one or multiple instances are used.
- When objects are created.
- When objects are destroyed.
- Whether state is shared across requests or sessions.
- Whether a dependency is recreated on each lookup.
- Whether scope-specific initialization and destruction callbacks execute as in the real application.

For example, a prototype object with an internal counter:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class OperationCounter {

    private int count;

    public int next() {
        return ++count;
    }
}
~~~

With a real prototype, two lookups create two objects:

~~~java
var first = context.getBean(OperationCounter.class);
var second = context.getBean(OperationCounter.class);

assertNotSame(first, second);
assertEquals(1, first.next());
assertEquals(1, second.next());
~~~

If the bean is replaced by a singleton mock, assertions about identity and state no longer reflect the original scope.

Therefore, when using Framework 7.0 to replace a non-singleton, treat it as a deliberate choice to isolate a dependency for a specific test. If the test's goal is to verify the prototype or scoped bean lifecycle itself, keep the real scope and test through the container.

## 7. What Is a FactoryBean?

FactoryBean is a Spring contract that allows one object to produce another object to be managed by the container. When a bean definition uses a FactoryBean, the normal bean name points to the object produced by the factory. To retrieve the factory object itself, prefix the bean name with &.

Example:

~~~java
public class RemoteClientFactoryBean
        implements FactoryBean<RemoteClient> {

    @Override
    public RemoteClient getObject() {
        return new DefaultRemoteClient();
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
~~~

Registering the factory:

~~~java
@Configuration(proxyBeanMethods = false)
class RemoteClientConfiguration {

    @Bean
    RemoteClientFactoryBean remoteClient() {
        return new RemoteClientFactoryBean();
    }
}
~~~

There are two objects to distinguish:

~~~text
ApplicationContext
      |
      +-- remoteClient (FactoryBean)
      |        |
      |        +-- getObject()
      |                |
      |                v
      |          RemoteClient product
      |
      +-- getBean("remoteClient")   -> RemoteClient product
      |
      +-- getBean("&remoteClient")  -> RemoteClientFactoryBean
~~~

Ways to access them:

~~~java
RemoteClient client =
        context.getBean("remoteClient", RemoteClient.class);

FactoryBean<?> factory =
        context.getBean("&remoteClient", FactoryBean.class);
~~~

FactoryBean's isSingleton() method describes the scope of the product created by the factory. It is not the way to declare the scope of the factory object itself. This is a common point of confusion when analyzing singleton behavior.

## 8. When Replacing a Bean Created by a FactoryBean

In bean overriding, distinguish between the replace strategy and the wrap strategy.

### 8.1. @MockitoBean Replaces the Product and Replaces the FactoryBean in the Context

Suppose RemoteClientFactoryBean produces RemoteClient. A test wants to replace RemoteClient with a mock:

~~~java
@SpringBootTest
class RemoteClientConsumerTest {

    @MockitoBean(enforceOverride = true)
    private RemoteClient remoteClient;
}
~~~

Spring identifies the bean by the product type RemoteClient. When replacing a bean created by a FactoryBean, the override infrastructure replaces the FactoryBean registration itself with a singleton bean corresponding to the mock product type.

Components injecting RemoteClient receive the Mockito mock as a result. The factory is no longer the object producing the product in the test context for that overridden bean.

Understand that the test replaces the product used by the application rather than testing the internal logic of RemoteClientFactoryBean.

### 8.2. @MockitoSpyBean Spies on the Product Created by the FactoryBean

If you use:

~~~java
@SpringBootTest
class RemoteClientSpyTest {

    @MockitoSpyBean
    private RemoteClient remoteClient;
}
~~~

Spring creates a spy from the object produced by the FactoryBean. The spy wraps the RemoteClient product, not RemoteClientFactoryBean.

As a result:

- Calls to RemoteClient can be observed with Mockito.
- The factory's getObject() logic does not automatically become a spy target.
- The test cannot use the RemoteClient field to verify internal calls on the factory.
- The factory may be initialized early to obtain the product to wrap.

If the goal is to test that the factory creates the right product, test the factory separately or use a context test that keeps the real factory and verifies the created product. If the goal is to isolate the consumer from the remote client, overriding the product with a mock is more suitable.

### 8.3. @TestBean Also Replaces the FactoryBean Based on the Product

@TestBean replaces a bean with the object returned by a test's static factory method. If the target bean is a product created by a FactoryBean, the infrastructure replaces the FactoryBean registration with a singleton bean corresponding to the object supplied by the test factory method.

Example:

~~~java
@SpringBootTest
class RemoteClientConsumerTest {

    @TestBean
    private RemoteClient remoteClient;

    static RemoteClient remoteClient() {
        return new FakeRemoteClient();
    }
}
~~~

The test uses FakeRemoteClient in place of the product. It does not test RemoteClientFactoryBean.getObject().

## 9. Scope of the FactoryBean and Scope of the Product

A FactoryBean can produce either a singleton product or a non-singleton product. Inspect both the bean definition and the isSingleton() method to understand the lifecycle.

Singleton product example:

~~~java
@Override
public boolean isSingleton() {
    return true;
}
~~~

Spring caches the product and returns the same product on ordinary lookups within the context.

If the factory returns:

~~~java
@Override
public boolean isSingleton() {
    return false;
}
~~~

Spring does not treat the product as a singleton. Retrieving the product can create a new instance according to the FactoryBean contract.

This matters when a bean override targets the product:

- With Framework 6.2.x, if the product is treated as non-singleton, the bean override is rejected under the singleton restriction.
- With Framework 7.0, when overriding the product via a bean override, the factory registration is replaced with a singleton override instance.
- With @MockitoSpyBean, the spy is created on the product produced by the factory; it does not turn the factory itself into a spy.

Therefore, do not infer the product's scope solely from the FactoryBean class name. Check isSingleton() and how the bean is registered.

## 10. Complete Example: Replacing RemoteClient Created by a FactoryBean

Suppose the application has an interface:

~~~java
public interface RemoteClient {
    RemoteResult fetch(String id);
}
~~~

Factory creating the client:

~~~java
public class RemoteClientFactoryBean
        implements FactoryBean<RemoteClient> {

    @Override
    public RemoteClient getObject() {
        return new HttpRemoteClient();
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
~~~

Consumer:

~~~java
@Service
public class RemoteDataService {

    private final RemoteClient remoteClient;

    public RemoteDataService(RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }

    public RemoteResult load(String id) {
        return remoteClient.fetch(id);
    }
}
~~~

Test replacing the product with a mock:

~~~java
@SpringBootTest
class RemoteDataServiceTest {

    @Autowired
    private RemoteDataService remoteDataService;

    @MockitoBean(enforceOverride = true)
    private RemoteClient remoteClient;

    @Test
    void shouldReturnRemoteResult() {
        var expected = new RemoteResult("item-1", "ready");

        when(remoteClient.fetch("item-1"))
                .thenReturn(expected);

        var actual = remoteDataService.load("item-1");

        assertEquals(expected, actual);
        verify(remoteClient).fetch("item-1");
    }
}
~~~

The test keeps RemoteDataService real and replaces the RemoteClient product dependency. It does not need to open a real HTTP connection.

If you want to test the factory, write a separate test:

~~~java
class RemoteClientFactoryBeanTest {

    @Test
    void shouldCreateRemoteClientProduct() throws Exception {
        var factory = new RemoteClientFactoryBean();

        var client = factory.getObject();

        assertNotNull(client);
        assertEquals(RemoteClient.class, factory.getObjectType());
        assertTrue(factory.isSingleton());
    }
}
~~~

The second example instantiates the factory directly and checks its contract. When you need to verify that Spring registers the factory and resolves the product by bean name, you can add a context test using the real factory configuration.

## 11. How Target Beans Are Located: Type, Qualifier, and Bean Name

The bean override infrastructure must clearly identify which bean will be replaced. Normally, Spring infers it from the type of the annotated field or parameter. If multiple beans share the same type, add a qualifier or name.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
~~~

The test specifies the exact bean to replace:

~~~java
@SpringBootTest
class CardPaymentServiceTest {

    @MockitoBean
    @Qualifier("cardPaymentGateway")
    private PaymentGateway paymentGateway;
}
~~~

Or specify the bean name in the annotation:

~~~java
@MockitoBean(name = "cardPaymentGateway")
private PaymentGateway paymentGateway;
~~~

When using a field-level annotation, the field name can also serve as a fallback qualifier if @Qualifier is omitted.

With class-level declarations, the type to replace is provided via the types attribute:

~~~java
@SpringBootTest
@MockitoBean(types = PaymentGateway.class, name = "cardPaymentGateway")
class CardPaymentServiceTest {
}
~~~

A practical rule: if a test cares about a specific implementation, declare the qualifier or bean name explicitly. That prevents replacing the wrong bean when the application adds new implementations.

## 12. Distinguishing Bean Overriding from Allowing Duplicate Bean Definitions

Two mechanisms are frequently confused:

**Bean overriding in Spring TestContext**

- Uses @TestBean, @MockitoBean, @MockitoSpyBean.
- Has strategies REPLACE, REPLACE_OR_CREATE, WRAP.
- Has specific rules for scope, FactoryBean, and bean selection.
- Handled by Spring's test infrastructure.

**Bean definition overriding in the container**

- Occurs when a new bean definition reuses an already-registered name.
- Relates to DefaultListableBeanFactory and the allowBeanDefinitionOverriding flag.
- Is a general container configuration behavior.
- Does not replace the specialized rules for test bean overriding.

Example Spring Boot configuration:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

This property does not turn a prototype bean into a valid target for @MockitoBean replacement in Framework 6.2.x. Nor does it change TestContext's FactoryBean handling rules.

Do not enable duplicate bean definition overriding just to bypass scope errors or replace mocks. Identify which mechanism caused the error and choose the API tailored to that mechanism.

## 13. Differences Across Spring Framework and Spring Boot Versions

Bean-replacement APIs in tests have changed significantly across versions. The table below helps select the right annotation and understand the exact behavior.

| Platform | Commonly Used API | Scope Rules and Notes |
|---|---|---|
| Spring Framework 6.1 and earlier | Lacks Framework 6.2's @TestBean, @MockitoBean, @MockitoSpyBean suite | Spring Boot projects typically use Boot's @MockBean/@SpyBean; or dedicated test configuration |
| Spring Framework 6.2.x | @TestBean, @MockitoBean, @MockitoSpyBean | Bean overrides accept singletons only; non-singletons throw an exception |
| Spring Boot 3.4.x and 3.5.x | Can use Framework 6.2 annotations | Boot's @MockBean and @SpyBean deprecated since 3.4.0, slated for removal in Boot 4.0 |
| Spring Framework 7.0.x | Continues using @TestBean, @MockitoBean, @MockitoSpyBean | When replacing non-singletons, Spring converts the bean definition to a singleton override |
| Spring Boot 4.0.x | Uses Spring Framework's bean override annotations | Use @MockitoBean and @MockitoSpyBean; check the migration guide for the exact Boot version |

### 13.1. Before Spring Framework 6.2

Spring Framework TestContext's @MockitoBean and @MockitoSpyBean annotations were introduced in Framework 6.2.

In older Spring Boot projects, the familiar approach is:

~~~java
@SpringBootTest
class OrderServiceTest {

    @MockBean
    private PaymentGateway paymentGateway;
}
~~~

@MockBean belongs to the package:

~~~text
org.springframework.boot.test.mock.mockito.MockBean
~~~

You cannot replace this import with org.springframework.test.context.bean.override.mockito.MockitoBean if the Spring Framework version in use does not yet include the new annotation.

### 13.2. Spring Framework 6.2 and Spring Boot 3.4

With Framework 6.2, you can use:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
~~~

Example:

~~~java
@SpringBootTest
class OrderServiceTest {

    @MockitoBean
    private PaymentGateway paymentGateway;
}
~~~

Spring Boot 3.4.0 deprecated Boot's @MockBean and @SpyBean in favor of the Spring Framework annotations. They are announced as deprecated for removal in Boot 4.0.0.

Therefore, for Boot 3.4 or 3.5 projects, prefer the Framework annotations if there are no specific compatibility constraints. During upgrades, inspect imports to avoid accidentally continuing to use the old annotations from the Spring Boot package.

### 13.3. Spring Framework 7.0 and Spring Boot 4.0

Framework 7.0 retains the Framework bean override annotations and updates behavior for non-singleton beans. When replacing a prototype or scoped bean, the override instance is managed as a singleton and the bean definition's scope is converted to singleton.

This means a test that previously failed on Framework 6.2 may pass on Framework 7.0. However, a passing test does not mean it accurately simulates production scope.

When upgrading, audit tests using @MockitoBean, @MockitoSpyBean, or @TestBean on prototype, request, session, and custom-scoped beans. Those tests may change meaning because the mock or fake is now shared as a singleton.

## 14. @MockitoSpyBean with Scoped Proxies

A scoped proxy is a proxy created by Spring to let a singleton bean reference a shorter-lived bean, such as request scope.

Example:

~~~java
@Component
@RequestScope
public class CurrentRequestData {
}
~~~

Or declaring the proxy explicitly:

~~~java
@Component
@Scope(
        value = WebApplicationContext.SCOPE_REQUEST,
        proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class CurrentRequestData {
}
~~~

In Spring Framework 7.0, @MockitoSpyBean does not support directly spying on a scoped proxy. If a test tries to spy on a bean declared with a scoped proxy, Spring may throw an exception.

The reason is that a spy needs a real instance to wrap. A scoped proxy represents a target whose lifecycle depends on a request or session, so it cannot be treated like an ordinary instance that a spy retains across the entire context.

Suitable alternatives:

- Test the target class's logic using plain unit tests.
- Test request-scope behavior with a web integration test and a real request context.
- Replace a singleton collaborator inside the scoped bean if the goal is to isolate that collaborator.
- Design a clear interface or service boundary to test business logic without spying on a scoped proxy.

Do not change a request-scoped bean to singleton just to make @MockitoSpyBean work if the test requirement involves per-request state isolation.

## 15. Bean Overrides and Spring AOP Proxies

A bean may be wrapped by Spring with an AOP proxy to apply @Transactional, @Cacheable, @Retryable, or method security.

How overrides affect proxies:

- @MockitoBean and @TestBean replace the bean directly with the override instance. That instance does not go through all the same bean post-processing as the original production bean, so the original bean's AOP advice may no longer apply.
- @MockitoSpyBean uses the WRAP strategy. If the original bean needs an AOP proxy, the proxy can still be created wrapping the spy as its target.

Conceptual diagram:

~~~text
@MockitoBean / @TestBean
        |
        v
Caller -> Override instance
          (mock or fake)

@MockitoSpyBean
        |
        v
Caller -> Spring AOP proxy
              |
              v
          Mockito spy
              |
              v
          Real instance
~~~

When testing transactions, caching, or retries, verify which object the test is calling. A replacement mock cannot prove that @Transactional on the original bean still works.

With a spy sitting behind an AOP proxy, stubbing can be affected by advice. For example, @Cacheable might cache an empty value while Mockito records the call used for stubbing. If you encounter this situation, you may need to unwrap the target spy with AopTestUtils.getUltimateTargetObject(...) to stub directly, or configure an appropriate test cache.

This is another reason to define your objective clearly: if you need to test real logic together with AOP, a spy may fit; if you only need to replace an external dependency, mocking at the boundary is usually simpler.

## 16. Sharing Singleton Mocks Across Tests

A bean override in the context can be shared by other beans and test classes through the ApplicationContext. Spring TestContext can also cache the context across test classes with equivalent configurations.

Consequently, a singleton mock can be shared within the context scope. The end of a test method does not mean the ApplicationContext and bean overrides are destroyed.

Several consequences:

- Stubbing and invocation history need to be reset according to the mock configuration.
- Tests should not depend on execution order.
- Do not let multiple parallel tests mutate a shared mock concurrently.
- Be careful with @TestInstance(PER_CLASS) and mutable fields.
- Keep bean override configurations consistent across classes to avoid creating unnecessary contexts.

The Spring TestContext documentation advises against running tests using @MockitoBean or @MockitoSpyBean in parallel, as concurrent interactions can produce unpredictable side effects.

If a test needs isolated state per invocation, create a separate fixture or mock within that scope, or intentionally use an isolated test context.

## 17. When You Need to Test Real Scope, Keep the Real Scope

If the test question is "does each prototype lookup return a new instance?", do not replace the bean with a singleton mock. Inspect the bean definition and container directly:

~~~java
@SpringJUnitConfig(PrototypeConfiguration.class)
class PrototypeScopeTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void shouldCreateANewInstanceForEachLookup() {
        var first = context.getBean(OperationCounter.class);
        var second = context.getBean(OperationCounter.class);

        assertNotSame(first, second);
    }
}
~~~

If you need to test request scope, create a separate request context for each scenario. In a Spring MVC integration test, you can send separate requests and verify that state does not leak between them.

If you need to test session scope, create separate sessions and verify that each session has its own state.

If you need to test a FactoryBean, keep the real factory and verify:

- getObject() returns a product of the right type.
- getObjectType() declares the right product type.
- isSingleton() accurately reflects the product's lifecycle.
- Lookups by bean name return the product according to the contract.
- Looking up &beanName returns the factory object.

These tests provide direct evidence about scope and factory lifecycle.

## 18. Alternatives When a Bean Cannot Be Overridden

If Framework 6.2 rejects a non-singleton bean or a test needs to preserve the original scope, choose another approach based on your goal.

**Test logic with unit tests**

Instantiate the object directly and pass fakes/mocks to its constructor. No ApplicationContext is needed if the question only concerns the class's logic.

**Keep the real scope in the context test**

Load the bean's real configuration, set up an appropriate request/session context, and verify behavior through the container.

**Mock a singleton dependency inside the scoped bean**

For example, keep RequestScopedService real while replacing the singleton RemoteClient it uses. That way the test preserves the request lifecycle and isolates network calls.

**Use an interface at the boundary to isolate**

If a bean has multiple responsibilities, extract external communication into a clear interface. The test replaces the collaborator at that boundary instead of replacing the scope-bound stateful bean.

**Use test configuration for new dependencies**

@TestConfiguration and @Import fit when you want to add supporting beans for tests. However, adding a bean to the context does not automatically replace an old bean. Check qualifiers, primary candidates, and bean names to ensure the application actually injects the desired implementation.

**Test the FactoryBean independently**

If the goal is product creation logic, instantiate the factory directly or create a small context with the real factory. If the goal is the consumer, replace the product type with a mock.

## 19. Strategy Selection Table by Scenario

| Scenario | Suitable Choice | What to Remember |
|---|---|---|
| Replace a singleton dependency with a mock | @MockitoBean | Use enforceOverride = true if the bean must exist |
| Observe a real singleton bean | @MockitoSpyBean | Requires a single unambiguous candidate |
| Replace a singleton with a custom fake | @TestBean | Static, no-argument factory method |
| Replace a prototype in Framework 6.2.x | Do not use bean override | Framework rejects non-singletons |
| Replace a prototype in Framework 7.0 | Can override | Replacement instance becomes a singleton |
| Verify a prototype creates new instances | Keep real bean and call container multiple times | Assert instance identity |
| Replace a product created by FactoryBean | Override the product type | FactoryBean registration is replaced when using replace strategy |
| Spy on a product created by FactoryBean | @MockitoSpyBean on product type | Spy wraps the product, not the factory |
| Test internal logic of a FactoryBean | Test the factory separately | Use &beanName when retrieving the factory from the context |
| Spy on a scoped proxy | Do not use @MockitoSpyBean directly | Test via real scope or replace an inner collaborator |
| Test AOP on a real bean | Keep the bean and consider a spy | A mock replacement may bypass AOP advice |
| Test has multiple implementations of an interface | @Qualifier or bean name | Avoid replacing the wrong candidate |

## 20. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Address |
|---|---|---|
| Context fails when using @MockitoBean | Target bean is non-singleton in Framework 6.2.x | Check scope and Framework version |
| Test passes after Framework upgrade, yet state behavior differs | Framework 7.0 converts non-singleton overrides to singleton | Re-examine assumptions about scope and state |
| @MockitoSpyBean reports multiple candidates | Could not identify a single unique bean | Use @Qualifier or bean name |
| Mock is created even though production bean does not exist | @MockitoBean uses REPLACE_OR_CREATE by default | Use enforceOverride = true |
| Spy makes real HTTP calls during stubbing | Stubbing invokes the real method | Use doReturn/doThrow or fake the dependency |
| Unable to test FactoryBean logic | Test is overriding the product | Keep the real factory and test it separately |
| Mock product works but factory does not run | Override replaced the FactoryBean registration | Test the factory in a separate context |
| Spying on a scoped proxy fails | @MockitoSpyBean does not support scoped proxies | Test target via request/session tests |
| @Transactional does not behave as expected | @MockitoBean replaced it with a bare mock | Keep the real bean or test the proxy in another test |
| Parallel tests fail randomly | Multiple tests share a mock in the context | Do not run tests using bean overrides in parallel, or isolate contexts |
| @MockitoBean annotation not found | Spring Framework version is too old | Check dependencies and use the version-appropriate API |

When investigating, check the actual Spring Framework version in the dependency tree. The Spring Boot version is only an initial clue; a project may override managed dependencies or use a different BOM. Verify the running spring-test artifact before drawing conclusions about behavior.

## 21. Safe Process for Choosing Bean Overrides

Before replacing a bean, determine the following information:

1. Is the injected bean an ordinary product or an object created by a FactoryBean?
2. Is the bean definition's scope singleton, prototype, request, session, or custom?
3. If it is a FactoryBean, what does the product's isSingleton() return?
4. Is the Spring Framework version 6.2.x or 7.0.x?
5. Does the test need to replace the bean with a mock, fake, or spy?
6. Does the test need to guard an existing production bean or allow creating a new bean?
7. Are there multiple candidates of the same type requiring a qualifier or bean name?
8. Does the bean have an AOP proxy or scoped proxy?
9. Does replacing the bean alter lifecycle, state, or parallel execution safety?
10. Is the test proving consumer, factory, or scope behavior?

After answering:

- Use @MockitoBean for dependencies that need mocking.
- Use enforceOverride = true when a missing bean must be an error.
- Use @MockitoSpyBean when observing a real implementation with exactly one candidate.
- Use @TestBean when replacing with a fake or test-constructed object.
- Keep the real bean when the test needs to verify scope or FactoryBean logic.
- Re-check tests after upgrading Framework because non-singleton rules changed.

## 22. Version-Specific References

Rules about singletons and FactoryBean should be checked against documentation for your exact version:

- [Bean Overriding in Tests — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [@MockitoBean and @MockitoSpyBean — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [BeanOverrideHandler — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/bean/override/BeanOverrideHandler.html)
- [Bean Overriding in Tests — Spring Framework 7.0](https://docs.spring.io/spring-framework/reference/7.0/testing/testcontext-framework/bean-overriding.html)
- [@MockitoBean and @MockitoSpyBean — Spring Framework 7.0](https://docs.spring.io/spring-framework/reference/7.0/testing/annotations/integration-spring/annotation-mockitobean.html)
- [@MockBean — Spring Boot 3.4 API and Deprecation Info](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [Mocking and Spying Beans — Spring Boot Testing](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

## 23. Conclusion

When replacing beans in Spring tests, scope and bean creation mechanism determine override behavior.

- Spring Framework 6.2.x allows bean overrides only for singletons; replacing prototype or scoped beans causes an error.
- Spring Framework 7.0 allows replacing non-singletons, but converts the bean definition to singleton. Mocks or fakes therefore no longer simulate the original lifecycle.
- For a FactoryBean, the replace strategy replaces the factory registration with a singleton override matching the product; the spy strategy wraps the product created by the factory.
- FactoryBean.isSingleton() describes the product's lifecycle, while &beanName retrieves the factory object.
- @MockitoBean, @MockitoSpyBean, and @TestBean use different strategies; choose the right one for the test goal.
- Spring Boot 3.4 deprecated @MockBean and @SpyBean in favor of Spring Framework annotations; projects must verify versions and imports when upgrading.

Keep the real scope when the goal is to verify bean lifecycle. When only isolating a dependency, replace the exact boundary and remember that singleton mocks can change how state is shared in the context. For FactoryBeans, always clarify whether the test works with the factory or the product before choosing a bean override style.

