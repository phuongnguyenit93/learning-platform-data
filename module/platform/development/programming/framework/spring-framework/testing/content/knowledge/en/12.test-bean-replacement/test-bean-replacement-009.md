# Interaction Between Bean Overrides and Spring AOP Proxies

The Spring TestContext Framework lets you replace a bean in the ApplicationContext with a Mockito mock or spy. Spring AOP can also wrap a bean in a proxy to execute advice such as transactions, caching, security, logging, or auditing. When these two mechanisms appear together, the test needs to know clearly whether it is calling a mock, a spy, a proxy, or the target object.

A bean replaced in a test can change the call path. If you replace the very service to which AOP applies with a mock, the test no longer checks the service's real logic and may no longer verify advice such as transactions or caching. If you use a spy on an already-proxied bean, the test must pay attention to which object Mockito is observing and which object Spring uses to apply advice.

This lesson explains how bean overrides interact with Spring AOP proxies, how to choose the right object to replace, how to verify that advice still executes, and how to diagnose cases where Mockito verification does not match the proxy or target.

## 1. Distinguishing Target, Proxy, and Overridden Bean

Spring AOP typically applies advice through a proxy. An external call passes through the proxy before reaching the target object:

~~~text
Caller
  |
  v
Spring AOP proxy
  |
  +--> Advice: transaction
  |
  +--> Advice: security
  |
  +--> Advice: cache / audit / logging
  |
  v
Target object
  |
  v
Business method
~~~

Each component has a distinct role:

- **Target** is the object executing business logic.
- **AOP proxy** is the object sitting in front of the target to orchestrate advice.
- **Advice** is the behavior executed before, after, or around a method invocation.
- **Bean override** is a test-time mechanism that replaces or wraps a bean in the ApplicationContext with a test double.
- **Mockito mock/spy** is an object managed by Mockito to provide simulated responses or track invocations.

In an application without AOP, bean references usually point directly to the target. When AOP is enabled, the reference injected into a collaborator is usually a proxy. The test calls methods on the proxy; Spring runs advice and then delegates the call to the target.

Bean overrides add another layer of indirection. They can replace the bean with a mock or wrap an existing bean with a spy. Therefore, do not assume that a variable injected into a test is always the original target or always an AOP proxy.

## 2. Two Common Bean Override Strategies

Spring Framework 6.2 added Mockito bean override annotations in Spring TestContext:

- **@MockitoBean** creates a Mockito mock and registers it to replace a matching bean in the ApplicationContext. When used on a field, the annotation can create a bean if no matching bean exists; you can set **enforceOverride = true** when the test requires a bean to already exist to be replaced.
- **@MockitoSpyBean** wraps an existing bean with a Mockito spy. Because it must wrap an existing implementation, the test must have a matching bean in the context; spies are supported for singleton beans.

Both annotations belong to the package:

~~~java
org.springframework.test.context.bean.override.mockito
~~~

Example replacing a repository with a mock:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {

    @MockitoBean
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void loadsOrderUsingMockRepository() {
        when(orderRepository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        Order order = orderService.findById("order-17");

        assertEquals("order-17", order.id());
        verify(orderRepository).findById("order-17");
    }
}
~~~

OrderService remains a real bean. Only OrderRepository is replaced with a mock. This is usually the right choice when the goal is to test service logic while controlling data returned by the repository.

Example wrapping a bean with a spy:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceSpyTest {

    @MockitoSpyBean
    private OrderService orderService;

    @Test
    void observesCallToRealService() {
        orderService.findById("order-17");

        verify(orderService).findById("order-17");
    }
}
~~~

The spy preserves the bean's real behavior by default and lets Mockito track invocations or stub part of its behavior. If the bean is also wrapped by a Spring AOP proxy, clarify whether the spy tracks the proxy layer or the target and make sure the test calls through the exact reference under test.

## 3. What Happens When @MockitoBean Replaces an AOP-Advised Bean?

Suppose OrderService has **@Transactional** or an audit aspect applied. During normal application execution, Spring may inject a proxy instead of the target. The proxy orchestrates advice before invoking the service method.

If a test uses **@MockitoBean** to replace OrderService itself, the bean supplied to the test is a mock. OrderService's real logic is no longer the primary execution path of the call. As a result:

- Business branches inside OrderService do not execute.
- Repositories or collaborators used by the real service may not be called.
- Assertions about the service's business outputs no longer reflect the real implementation.
- The test cannot use a mock service to prove that transactions or caching on the real service work properly.

Do not infer that because the mock bean has the same type as the service, all AOP behavior of the real service must still be intact. Bean overriding changes the object supplied by the context; actual proxies and advice also depend on configuration and bean processing order in the context. If the goal is to verify AOP on the service, keep the service real and replace collaborators beneath it.

### Recommended Pattern: Keep the Service Real, Mock Collaborators

~~~java
@SpringJUnitConfig(OrderAopTestConfig.class)
class OrderServiceAopTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void runsRealServiceWithControlledRepository() {
        when(orderRepository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        orderService.confirm("order-17");

        verify(orderRepository).save(any(Order.class));
    }
}
~~~

Here, OrderService is created from the Spring configuration and still executes real logic. The repository is mocked so the test controls data and verifies interactions. If OrderService has AOP applied, the test can continue calling through the service's proxy bean.

The **enforceOverride = true** attribute is useful when the test wants to fail if there is no OrderRepository bean to replace. That prevents the test from accidentally creating a new mock when the context configuration is missing the production repository the test expected to check.

## 4. Proxies Can Be JDK Dynamic Proxies or CGLIB Proxies

Spring AOP typically creates one of two proxy forms:

| Proxy Type | Characteristics | Testing Implications |
|---|---|---|
| JDK dynamic proxy | Proxy based on interfaces implemented by the target | Inject and invoke the bean via its interface |
| CGLIB proxy | Creates a subclass of the target class | Can inject by class, but constrained by final classes/methods and subclassing rules |

If a bean uses a JDK proxy, the injected reference may not be an instance of the concrete implementation class. Tests should depend on the interface exposed by the bean.

Example:

~~~java
public interface OrderOperations {
    void confirm(String orderId);
}

public class OrderService implements OrderOperations {

    @Override
    public void confirm(String orderId) {
        // Business logic
    }
}
~~~

The test can inject via the interface:

~~~java
@Autowired
private OrderOperations orderOperations;
~~~

This avoids casting the proxy to OrderService when the proxy only exposes the interface. If you need to inspect the proxy, Spring provides utilities in **AopUtils**:

~~~java
assertTrue(AopUtils.isAopProxy(orderOperations));
Class<?> targetClass = AopUtils.getTargetClass(orderOperations);
assertEquals(OrderService.class, targetClass);
~~~

**AopUtils.isAopProxy(...)** indicates whether a reference is an AOP proxy. **AopUtils.getTargetClass(...)** helps determine the target class represented by the proxy. These two checks are useful when a test needs to prove that a bean is configured via AOP.

Do not test for a proxy by comparing the runtime class against the implementation class. With a JDK proxy, the runtime class is a proxy class; with CGLIB, the runtime class is a dynamically generated subclass.

## 5. Interaction Between @MockitoSpyBean and AOP Proxies

**@MockitoSpyBean** uses the wrap strategy: Spring takes an existing bean and wraps it in a Mockito spy. If the bean is already AOP-proxied, wrapping can create a multi-layered relationship between the spy and the proxy. The test must distinguish:

- The reference provided by the ApplicationContext to consumers.
- The object on which Mockito is recording calls.
- The target object behind the AOP proxy.
- Whether advice runs when a call passes through that reference.

Invoke the bean through the reference injected by Spring if the goal is to verify application behavior. Then use Mockito verify on the exact spy supplied by Spring.

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceSpyTest {

    @MockitoSpyBean
    private OrderService orderService;

    @Test
    void recordsInvocationOnSpiedBean() {
        orderService.findById("order-17");

        verify(orderService).findById("order-17");
    }
}
~~~

This example illustrates verifying calls on a spy. If the bean is also AOP-proxied, add assertions on advice or side effects to prove the proxy chain works; merely verifying that the method was called is not enough to prove that transaction, security, or cache advice executed.

### Do Not Call the Target Directly When Testing Advice

If you unwrap the target object behind a proxy and call it directly, the call can bypass the proxy and thus bypass advice. Example:

~~~java
Object target = AopTestUtils.getUltimateTargetObject(orderService);
~~~

Retrieving the target is useful for diagnostics or certain specific Mockito verification cases. However, calling methods on **target** instead of the proxied bean means the test no longer tests the normal AOP call path.

Follow these rules:

- Call methods through the proxied bean when verifying advice.
- Access the target only when inspecting proxy structure or handling a specific verification case.
- Do not use a target reference in place of the bean in tests designed to verify transactions, security, or caching.

## 6. Spying on an Aspect's Collaborator to Verify Advice

An approach less coupled to proxy layering is keeping the AOP-advised bean real while spying on a collaborator called by the advice.

Example aspect recording an event after OrderService confirms an order:

~~~java
@Aspect
class OrderAuditAspect {

    private final AuditRecorder auditRecorder;

    OrderAuditAspect(AuditRecorder auditRecorder) {
        this.auditRecorder = auditRecorder;
    }

    @AfterReturning(
        pointcut = "execution(* example.OrderService.confirm(..)) && args(orderId)"
    )
    public void recordConfirmation(String orderId) {
        auditRecorder.record("confirmed:" + orderId);
    }
}
~~~

Test configuration:

~~~java
@Configuration
@EnableAspectJAutoProxy
class OrderAopTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }

    @Bean
    AuditRecorder auditRecorder() {
        return new AuditRecorder();
    }

    @Bean
    OrderAuditAspect orderAuditAspect(AuditRecorder recorder) {
        return new OrderAuditAspect(recorder);
    }
}
~~~

The test replaces the repository and spies on the recorder, while keeping the service and aspect real:

~~~java
@SpringJUnitConfig(OrderAopTestConfig.class)
class OrderAuditAspectTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository orderRepository;

    @MockitoSpyBean
    private AuditRecorder auditRecorder;

    @Autowired
    private OrderService orderService;

    @Test
    void executesAuditAdviceThroughSpringProxy() {
        when(orderRepository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        assertTrue(AopUtils.isAopProxy(orderService));

        orderService.confirm("order-17");

        verify(auditRecorder).record("confirmed:order-17");
    }
}
~~~

The example assumes pointcuts and models match the project's packages. The key idea is that the test calls OrderService from the ApplicationContext so Spring AOP orchestrates the advice. The Mockito spy observes only the AuditRecorder used by the advice. This lets the test verify that the advice was invoked without spying directly on the service proxy.

If **@MockitoSpyBean** cannot find a unique AuditRecorder bean, declare a qualifier or adjust the configuration to provide a single target bean. A spy requires an existing bean to wrap.

## 7. Testing @Transactional When a Service Has Bean Overrides

**@Transactional** is typically enforced through a Spring AOP proxy. When a method is called externally through the proxy, the transaction interceptor can start, join, or complete a transaction according to configuration.

If you replace the **@Transactional** service itself with **@MockitoBean**, the test no longer verifies the transaction boundary of the real service implementation. To test transactions, keep the service real and replace the repository or a collaborator other than the object being verified.

Example service checking transaction status inside a method:

~~~java
@Service
public class TransactionProbeService {

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }
}
~~~

Test configuration must enable transaction management and provide a transaction manager:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionTestConfig {

    @Bean
    PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    TransactionProbeService transactionProbeService() {
        return new TransactionProbeService();
    }
}
~~~

Test invoking the bean from the context:

~~~java
@SpringJUnitConfig(TransactionTestConfig.class)
class TransactionProxyTest {

    @Autowired
    private TransactionProbeService transactionProbeService;

    @Test
    void startsTransactionThroughProxy() {
        assertTrue(AopUtils.isAopProxy(transactionProbeService));
        assertTrue(transactionProbeService.isTransactionActive());
    }
}
~~~

The example requires a DataSource and matching transaction dependencies in the test context. In real projects, an appropriate test database or transaction manager can be used. The assertion verifies that a transaction is active inside the call, not merely that the bean has a proxy.

If you need to mock a repository called inside the transaction, use **@MockitoBean** on the repository while still calling the real service. That way, the test controls the collaborator while preserving the path through the transaction proxy.

## 8. Testing Cache and Security Advice

The same principle applies to other advice types.

### Cache

If a method has **@Cacheable**, calling through the proxy exercises the cache interceptor. If you replace the service containing that method with a mock, the test no longer proves the caching behavior of the real implementation.

A cache test can:

1. Keep the real service in the context.
2. Use a spy or mock for the underlying repository.
3. Call the same method twice through the Spring bean.
4. Verify the repository is queried only according to the configured cache policy.
5. Clear the cache between tests to avoid shared state.

Illustrative example:

~~~java
@SpringJUnitConfig(CacheTestConfig.class)
class OrderCacheTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository repository;

    @Autowired
    private OrderQueryService queryService;

    @Autowired
    private CacheManager cacheManager;

    @Test
    void cachesRepeatedLookup() {
        when(repository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        queryService.findById("order-17");
        queryService.findById("order-17");

        verify(repository, times(1)).findById("order-17");
    }

    @AfterEach
    void clearCache() {
        cacheManager.getCache("orders").clear();
    }
}
~~~

The example assumes an **orders** cache is configured and the service method has **@Cacheable** with the matching key. If the cache key, condition, or cache manager differs, the expected invocation count must reflect the project's actual configuration.

### Security

With method security, a proxy can check authorization before invoking a method. If you replace the protected service with a mock, the test may skip the exact method interception that needs to be verified.

Keep the protected bean real in the context, replace collaborators such as repositories or permission lookups if you need to control data, and invoke through the injected bean. Verify both permitted outcomes and denial exceptions with an appropriate security configuration.

Do not treat verifying a mock collaborator as proof that security advice executed. Verify security behavior directly at the proxy boundary.

## 9. AOP Self-Invocation Remains a Limitation

A Spring AOP proxy normally intercepts external calls entering a bean. When a method on the target calls another method on the same object via **this**, that internal call does not pass through the proxy again.

Example:

~~~java
@Service
class ReportService {

    public void generate() {
        saveReport();
    }

    @Transactional
    public void saveReport() {
        // Save report
    }
}
~~~

If **generate()** is called through the proxy, the internal **this.saveReport()** call inside the target does not re-enter the proxy. Thus, transaction advice on **saveReport()** may not be applied as expected.

Using **@MockitoSpyBean** does not automatically fix the self-invocation limitation. A spy can record the method invocation, yet that does not prove the call went through the AOP proxy and executed advice.

A common design approach is extracting the advised method into a separate collaborator:

~~~java
@Service
class ReportWriter {

    @Transactional
    public void saveReport() {
        // Save report
    }
}

@Service
class ReportService {

    private final ReportWriter reportWriter;

    ReportService(ReportWriter reportWriter) {
        this.reportWriter = reportWriter;
    }

    public void generate() {
        reportWriter.saveReport();
    }
}
~~~

When ReportService calls ReportWriter through the injected proxy bean, the call can pass through transaction advice. Tests can keep ReportWriter real and test transactions, or mock at another boundary depending on the goal.

## 10. Verifying the Exact Object with AopUtils and AopTestUtils

When Mockito reports a verification error or a test does not observe advice, identify which object is actually being used.

Spring provides these utilities:

| API | Purpose |
|---|---|
| **AopUtils.isAopProxy(bean)** | Checks whether a bean is an AOP proxy |
| **AopUtils.isJdkDynamicProxy(bean)** | Checks for a JDK interface-based proxy |
| **AopUtils.isCglibProxy(bean)** | Checks for a CGLIB proxy |
| **AopUtils.getTargetClass(bean)** | Gets the target class represented by the proxy |
| **AopTestUtils.getTargetObject(bean)** | Gets the immediate target if the bean is an applicable proxy |
| **AopTestUtils.getUltimateTargetObject(bean)** | Walks through nested proxy layers to get the final target |

Diagnostic example:

~~~java
@Autowired
private OrderOperations orderOperations;

@Test
void inspectsProxyType() {
    assertTrue(AopUtils.isAopProxy(orderOperations));

    Class<?> targetClass = AopUtils.getTargetClass(orderOperations);
    assertEquals(OrderService.class, targetClass);

    if (AopUtils.isJdkDynamicProxy(orderOperations)) {
        assertTrue(orderOperations instanceof OrderOperations);
    }
}
~~~

These utilities help inspect proxy structure. They do not replace behavioral tests of advice. If a test calls the target directly after unwrapping it from the proxy, advice may be bypassed.

### When Mockito Verify Reports That the Object Is Not a Mock

An error can occur when a test calls **verify(...)** on a proxy or target different from the Mockito spy created by the annotation. Check:

1. Which field is annotated with **@MockitoSpyBean**?
2. Which bean reference is the consumer calling from the ApplicationContext?
3. Is the bean wrapped in an AOP proxy or nested proxies?
4. At which layer in the wrapper chain does the Mockito spy sit?
5. Is the test calling the target directly instead of the proxied bean?

Only use **AopTestUtils** when you need to confirm that a target is actually the Mockito spy. You cannot call **verify(...)** on just any target object merely because you unwrapped it from a proxy; that object must be a Mockito mock or spy.

If a test needs to verify advice, prefer verifying the advice's side effect through a separate collaborator or probe. This approach depends far less on wrapper ordering between Mockito and Spring AOP.

## 11. Advice Order and Wrapper Order Are Two Different Concerns

Spring AOP can apply multiple advisors to the same bean. Advice execution order depends on advisor order configuration and interceptor chain rules.

A Mockito spy, by contrast, is a wrapper for observing invocations. Whether the spy wraps the proxy or the proxy wraps the spy is a question of object structure managed within the test context.

Do not confuse them:

- **Advice order** determines the order in which Spring AOP interceptors execute.
- **Wrapper order** determines the path calls take through the Mockito spy and the AOP proxy.
- **Bean override strategy** determines whether a bean is replaced or wrapped.

If advice order has business significance, assert the observable outcome of the advice or write a dedicated aspect test. Do not infer advice order solely from Mockito verification order.

For example, a call might pass through transaction advice and then audit advice, or in the reverse order depending on advisor configuration. If order must be guaranteed, set explicit order on the advisors and write tests checking events or state that demonstrate that order.

## 12. Using @MockitoBean for Collaborators Inside an AOP Target

A useful pattern is replacing a collaborator called by the target while keeping the AOP-advised bean real:

~~~text
Test
 |
 v
AOP proxy of OrderService
 |
 +--> Transaction / Audit advice
 |
 v
Real OrderService
 |
 v
MockitoBean: OrderRepository
~~~

In this structure:

- The service still runs its real implementation.
- The AOP proxy remains the call path from the test into the service.
- The repository is replaced by a mock to control outcomes and verify interactions.
- Advice can be tested via transaction state or dedicated side effects.

This is a good fit when a test wants to combine real logic, simulated collaborators, and AOP infrastructure.

Example:

~~~java
@SpringJUnitConfig(OrderModuleTestConfig.class)
class OrderServiceProxyTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository repository;

    @Autowired
    private OrderOperations orderOperations;

    @Test
    void invokesRepositoryThroughRealServiceProxy() {
        when(repository.findById("order-22"))
                .thenReturn(Optional.of(new Order("order-22")));

        assertTrue(AopUtils.isAopProxy(orderOperations));

        orderOperations.confirm("order-22");

        verify(repository).save(any(Order.class));
    }
}
~~~

This test verifies that the service bean is proxied and that the mock repository receives the call. If you want to verify a specific advice, add assertions about the behavior produced by that advice. **isAopProxy** only confirms that a proxy exists, not that all advisors are properly configured.

## 13. Choosing Mock, Spy, or Real Bean by Scenario

| Test Objective | Appropriate Choice | What to Preserve |
|---|---|---|
| Test service logic | Real service, mock/fake collaborators | Service implementation |
| Test service transactions | Real service via proxy, test database or transaction manager | Transaction interceptor and real target |
| Test cache advice | Real service via proxy, mock repository | Cache interceptor and cache manager |
| Test security advice | Real protected bean via proxy | Method security configuration |
| Observe calls to a real bean | @MockitoSpyBean | Exact spy reference and call path |
| Observe an aspect's collaborator | @MockitoSpyBean on collaborator | Real service and aspect |
| Replace an external service | @MockitoBean on gateway/client | Service under test |
| Test an aspect independently | Aspect test with proxy and clear probe | Pointcut, advice, and observable outcomes |

Do not replace a bean simply because it has many dependencies. Identify which bean is the subject under test and which beans are replaceable boundaries.

## 14. Common Mistakes When Bean Overrides Interact with AOP

### Replacing the Bean Under Test with a Mock

The test may pass because the mock returns configured values, while real logic and advice go unverified. Keep the bean under test real and replace its collaborators.

### Assuming @MockitoBean Preserves the Target and Advice

A mock replaces the actual bean supplied by the context. Do not rely on the bean type name to assume that the target and full proxy chain still behave as in production. Inspect the proxy structure and specific advice behavior.

### Verifying the Wrong Proxy or Target

Mockito can only verify the corresponding mock/spy. If the test invokes the proxy yet verifies a different target, assertions may fail to observe the call. Use the exact reference injected by Spring or clearly identify the wrapper layer.

### Calling the Target Directly

Unwrapping the target with **AopTestUtils** and invoking methods directly can bypass advice. Only call through the target when the test's goal is not testing AOP.

### Spying on a Bean with Side Effects

A spy usually retains the real implementation. Methods may open transactions, send requests, write files, or publish messages. Control collaborators and data before calling.

### Injecting a Concrete Class When the Bean Uses a JDK Proxy

A JDK proxy may only implement interfaces. Inject via the interface, or configure class-based proxies if the architecture genuinely needs them and classes/methods satisfy CGLIB constraints.

### Confusing Self-Invocation with Calls Through a Proxy

A method calling another method on the same target does not automatically re-enter the proxy. A spy does not alter this rule. Extract collaborators or design appropriate method boundaries.

### Only Checking That a Proxy Exists

**AopUtils.isAopProxy(bean)** does not prove that transaction, cache, or security advice executed properly. Verify actual transaction state, repository access counts, cache outcomes, or access permissions.

### Using a Spy Instead of a Clear Aspect Test

If the goal is testing pointcuts or advice ordering, spying on a service can introduce tight coupling to proxy structure. A probe or spied collaborator usually provides clearer evidence.

## 15. Diagnostic Process When an AOP Test Fails

When a test involving bean overrides and AOP behaves unexpectedly, check in order:

1. **Identify the bean under test**: real service, collaborator, or aspect?
2. **Identify the override strategy**: mock replacing the bean or spy wrapping the bean?
3. **Check the context**: is the bean registered and in the right profile?
4. **Check the proxy**: use **AopUtils.isAopProxy** and **AopUtils.getTargetClass**.
5. **Check the proxy type**: JDK or CGLIB; is the test injecting via a compatible type?
6. **Check the call path**: does the call go through the bean from the ApplicationContext or hit the target directly?
7. **Check the pointcut**: do the method and class match the pointcut expression?
8. **Check the advisor**: is the aspect or transaction/cache/security configuration enabled?
9. **Check for self-invocation**: is the method called from outside the target?
10. **Check the Mockito reference**: is verify targeting the right configured mock/spy used in the test?

During diagnosis, logging the bean name, target class, and proxy status can help. Do not log sensitive data or collaborator credentials.

## 16. Checklist for Designing Tests with Bean Overrides and AOP

Before finalizing the test, confirm:

- Is the bean under test a real implementation that should be preserved?
- Have you accidentally replaced an advised service with **@MockitoBean**?
- Which collaborators can be mocked without losing the behavior under test?
- If using **@MockitoSpyBean**, does the bean exist and is it a singleton?
- Does the test call the bean through the reference supplied by Spring rather than calling the target directly?
- Does the bean have a JDK proxy or a CGLIB proxy?
- Are dependencies injected via interfaces when JDK proxy compatibility is needed?
- Do assertions prove that advice ran, rather than only proving a proxy exists?
- If verification fails, is Mockito observing the right spy reference?
- Is the test affected by self-invocation, cache state, transactions, or side effects?
- Are test data and dependent state isolated between tests?

## 17. Guiding Principle

When a test needs to verify business logic and AOP together, keep the target bean real in the ApplicationContext and replace non-central collaborators with **@MockitoBean**. If you need to observe a real bean, use **@MockitoSpyBean** intentionally and identify the exact spy reference. When testing advice, invoke methods through the Spring-supplied bean proxy and verify the effects produced by the advice.

Mocks, spies, and AOP proxies solve different problems. A mock replaces a bean's behavior with test-controlled responses; a spy observes an existing implementation; an AOP proxy orchestrates advice before calls reach the target. Understanding where each object sits on the method call path helps tests verify the right logic, the right interactions, and the right cross-cutting Spring behavior.

