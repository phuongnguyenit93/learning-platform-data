# Distinguishing the Test Instance from Context-Managed Beans

In a Spring test, two kinds of objects typically appear side by side: the test instance created by the testing framework and the beans managed by the Spring ApplicationContext. The test instance holds test methods, fixtures, mocks, and assertion helper fields. Beans are objects in the application graph that Spring instantiates, configures, injects, and manages throughout their scoped lifecycle.

Spring can inject beans into the test instance, yet being injected does not turn the test instance into an ApplicationContext bean. This is crucial for understanding the scope of @Autowired, @Mock, @Bean, @Configuration, and bean-replacement annotations. Confusing the two kinds of objects can lead to tests creating mocks while the service still uses a real bean, or accidentally sharing state across tests.

## 1. Two Mechanisms for Creating and Managing Objects

A test class is normally instantiated by JUnit Jupiter according to the configured test lifecycle. JUnit invokes test methods and callbacks such as @BeforeEach and @AfterEach. Spring participates through SpringExtension and the TestContext Framework to prepare the ApplicationContext, inject dependencies into the test instance, and provide features like test-managed transactions.

Meanwhile, the ApplicationContext is Spring's container. It creates beans from component scanning, @Bean methods, XML configuration, or other bean registration mechanisms. The container resolves dependencies between beans and manages their lifecycles according to scope.

| Characteristic | Test Instance | Bean Managed by ApplicationContext |
|---|---|---|
| Who creates it? | JUnit or the respective test framework | Spring container |
| Purpose | Holds test methods, fixtures, and assertions | Performs application or infrastructure work |
| How it receives dependencies | Spring can inject into the test instance; JUnit/Spring can supply constructor or method parameters | Spring resolves dependencies when creating the bean |
| Lifecycle | Follows JUnit test lifecycle and @TestInstance configuration | Follows bean scope and ApplicationContext lifecycle |
| Is it in the bean registry? | Not merely because the test instance uses SpringExtension or @Autowired | Yes, once registered in the context |
| Can it be shared? | Depends on JUnit lifecycle, typically one instance per method | Can be shared across tests when the context is cached and the bean is a singleton |

For example, a test class can have InventoryService injected by Spring:

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsAnInventoryItem() {
        // inventoryService is a Spring-managed bean.
    }
}
~~~

JUnit creates the InventoryServiceTest object to invoke the test method. Spring looks up the InventoryService bean in the context and assigns it to the test object's inventoryService field. The test class remains a JUnit test instance; InventoryService is the bean inside the context.

## 2. The Test Instance Receives Injection Without Becoming a Bean

The TestContext Framework includes a listener named DependencyInjectionTestExecutionListener. This listener prepares the test instance by asking Spring to autowire dependencies declared on the test class. Consequently, @Autowired fields or methods on the test class can receive beans from the ApplicationContext.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Autowired
    private InventoryService inventoryService;

    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    void loadsAnItem() {
        InventoryItem item = inventoryService.find("SKU-01");

        assertEquals("SKU-01", item.sku());
    }
}
~~~

Spring injects two beans into the test instance. That does not mean Spring registered InventoryServiceTest as a bean, nor does it mean the test class is component-scanned like a regular service.

Spring TestContext uses the ApplicationContext to resolve the beans to inject, while the test object itself is still created by the test framework. Spring only performs autowiring on an already-created object. That is why a test class can use @Autowired without placing @Component or @Service on the test class itself.

### Constructor Injection for Test Classes

With JUnit Jupiter, SpringExtension also supports supplying constructor or test method parameters from the context. You can use @TestConstructor to request autowiring for all constructor parameters:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestConstructor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class InventoryServiceConstructorTest {
    private final InventoryService inventoryService;

    InventoryServiceConstructorTest(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Test
    void findsAnItem() {
        InventoryItem item = inventoryService.find("SKU-01");

        assertEquals("SKU-01", item.sku());
    }
}
~~~

Constructor injection ensures required fixtures are declared right when the test instance is created. However, the test class still does not become a bean. Spring participates in resolving constructor parameters through JUnit integration; JUnit still manages creating and invoking the test instance.

Spring can also resolve parameters of test methods:

~~~java
@Test
void receivesAServiceAsParameter(InventoryService inventoryService) {
    assertNotNull(inventoryService);
}
~~~

This capability comes from SpringExtension's parameter resolver. Do not confuse a parameter being fetched from the context with the method or test class being a bean.

## 3. Beans Created and Managed Inside the ApplicationContext

A bean is an object known to and managed by the Spring container. Beans can be registered via component scanning, @Bean methods in a @Configuration class, or other configuration mechanisms.

For example, business and repository classes can be defined as follows:

~~~java
public record InventoryItem(String sku, int available) {
}

public interface InventoryRepository {
    InventoryItem findBySku(String sku);
}

public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public InventoryItem find(String sku) {
        return repository.findBySku(sku);
    }
}
~~~

A Spring configuration registers the beans:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {
    @Bean
    InventoryRepository inventoryRepository() {
        return new JdbcInventoryRepository();
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository inventoryRepository) {
        return new InventoryService(inventoryRepository);
    }
}
~~~

When the ApplicationContext is created, Spring invokes @Bean methods as needed to register and instantiate beans. The inventoryService method accepts an inventoryRepository parameter; Spring resolves the matching bean and passes it to the constructor. Both the InventoryRepository implementation and InventoryService belong to the context.

In tests, you can use a dedicated test configuration instead of the production configuration:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryTestConfig {
    @Bean
    InMemoryInventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository inventoryRepository) {
        return new InventoryService(inventoryRepository);
    }
}

class InMemoryInventoryRepository implements InventoryRepository {
    private final Map<String, InventoryItem> items =
            new ConcurrentHashMap<>();

    InMemoryInventoryRepository() {
        items.put("SKU-01", new InventoryItem("SKU-01", 8));
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return items.get(sku);
    }
}
~~~

InventoryTestConfig is a configuration used for testing. @Bean methods create InMemoryInventoryRepository and InventoryService. The objects returned from @Bean methods are registered by Spring in the context; the test class itself that uses the context remains a separate test instance.

In Spring Boot projects, @TestConfiguration is commonly used to add beans solely for testing. This configuration class can be a static nested class inside the test or explicitly imported. With plain Spring Framework, @Configuration combined with @ContextConfiguration or @SpringJUnitConfig suffices to declare the test context.

## 4. Distinguishing @Autowired on a Test from @Autowired on a Bean

The @Autowired annotation can appear on both test classes and application beans, yet the target receiving injection differs.

~~~java
@Service
public class CheckoutService {
    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

In this case, Spring injects PaymentGateway when instantiating the CheckoutService bean. This is part of building the bean graph.

~~~java
@SpringJUnitConfig(CheckoutTestConfig.class)
class CheckoutServiceTest {
    @Autowired
    private CheckoutService checkoutService;
}
~~~

In this case, Spring injects the CheckoutService bean into a field of the test instance. The test class is not added to the bean registry merely because of the @Autowired annotation.

You can look at the purpose of injection:

- On a bean's constructor: declares required dependencies for Spring to instantiate the bean.
- On a bean's field or method: asks Spring to inject during or after bean creation.
- On a test instance: asks TestContext to prepare the fixture with beans from the context.
- On a test method or test constructor parameter: asks SpringExtension to resolve the parameter from the context.

Constructor injection is generally the preferred way to declare required dependencies of a bean. On test classes, field injection remains common because the test framework creates the test instance first and Spring prepares it afterward; constructor injection is also available when properly configured.

## 5. @Mock Does Not Automatically Replace a Bean in the Context

A common mistake is declaring @Mock in a test class and expecting an application bean to automatically use that mock. Mockito's @Mock annotation only creates a mock object inside the test's fixture. It does not register the mock as a bean and does not replace dependencies already injected into another bean.

Consider the following example:

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Mock
    private InventoryRepository inventoryRepository;

    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsAnItem() {
        // inventoryService still holds the repository injected by Spring.
    }
}
~~~

Here, @Mock creates a mock InventoryRepository in the test instance. However, InventoryService was created inside the ApplicationContext from the test configuration and already received the repository bean resolved by Spring. The mock in the inventoryRepository field does not automatically change the reference inside InventoryService. If the test stubs the mock field and then calls inventoryService, the service may still call the other repository bean.

If you want to unit-test the service in isolation, instantiate the service yourself via its constructor:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class InventoryServiceUnitTest {
    @Mock
    private InventoryRepository repository;

    private InventoryService service;

    @BeforeEach
    void setUp() {
        service = new InventoryService(repository);
    }

    @Test
    void returnsTheItemFromTheRepository() {
        InventoryItem expected = new InventoryItem("SKU-01", 8);
        when(repository.findBySku("SKU-01")).thenReturn(expected);

        InventoryItem actual = service.find("SKU-01");

        assertEquals(expected, actual);
    }
}
~~~

This test needs no ApplicationContext. MockitoExtension creates the mock, while the test instantiates InventoryService and passes the mock to the constructor. The service is guaranteed to use the stubbed object.

## 6. Replacing a Bean in the Context with @MockitoBean

If the goal is testing a service inside a Spring context while replacing the repository bean with a mock, you must use a bean-override mechanism. Starting with Spring Framework 6.2, @MockitoBean can register a mock in place of a matching bean in the ApplicationContext.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceContextTest {
    @MockitoBean
    private InventoryRepository inventoryRepository;

    @Autowired
    private InventoryService inventoryService;

    @Test
    void usesTheMockBeanInjectedIntoTheService() {
        InventoryItem expected = new InventoryItem("SKU-01", 8);
        when(inventoryRepository.findBySku("SKU-01"))
                .thenReturn(expected);

        InventoryItem actual = inventoryService.find("SKU-01");

        assertEquals(expected, actual);
    }
}
~~~

In this example, @MockitoBean tells Spring TestContext to replace the InventoryRepository bean in the context with a Mockito mock. InventoryService is created by Spring and receives that very mock bean. Therefore, when the test stubs the inventoryRepository field and calls inventoryService, the service uses the configured result.

@MockitoBean belongs to the org.springframework.test.context.bean.override.mockito package and requires Spring Framework 6.2 or later. On older versions, projects can use the mock-bean mechanism provided by their Spring Boot version or configure an alternative test bean. Check actual dependency versions before choosing an annotation.

Other bean-override annotations can include:

- @MockitoSpyBean: wraps an existing bean in the context with a spy to preserve most real behavior while allowing selective verification or stubbing.
- @TestBean: replaces or supplies a bean using a factory method in the test, fitting when a fake or specific test implementation is needed.
- @MockitoBean: creates a mock and registers it into the context as a bean override.

These annotations affect the context's bean graph. They differ from Mockito's @Mock and @Spy, which only create objects inside the test's fixture.

## 7. Distinguishing Common Annotations

| Annotation | Which Mechanism? | Where Does It Create or Act? |
|---|---|---|
| @Autowired | Spring Core / TestContext | Injects beans into application beans or the test instance |
| @Component, @Service, @Repository | Spring component scanning | Registers application classes as beans |
| @Configuration | Spring configuration | Declares bean-producing configuration |
| @Bean | Spring configuration | Registers the object returned by a method as a bean |
| @TestConfiguration | Spring Boot Test | Adds configuration and beans used only for tests |
| @Mock | Mockito | Creates a mock in the test fixture |
| @Spy | Mockito | Creates a spy in the test fixture from a real object |
| @MockitoBean | Spring TestContext 6.2+ | Overrides or supplies a mock bean in the ApplicationContext |
| @MockitoSpyBean | Spring TestContext 6.2+ | Overrides a bean with a spy in the ApplicationContext |
| @TestBean | Spring TestContext 6.2+ | Overrides or supplies a bean via a test factory method |

Similar annotation names do not mean they share the same scope. Ask the right question before choosing:

- Need a mock to pass into a manually instantiated service? Use @Mock or Mockito.mock().
- Need a mock bean replacing a repository in the context? Use @MockitoBean if supported by your version.
- Need to keep the real bean while verifying or stubbing part of its behavior? Consider @Spy or @MockitoSpyBean depending on fixture vs. context scope.
- Need a working fake implementation like an in-memory repository? Create a fake and register it with @Bean in test configuration.

## 8. Test Instance Lifecycle vs. ApplicationContext Lifecycle

Another important difference lies in object lifetimes. With JUnit Jupiter, the default lifecycle is PER_METHOD: JUnit creates a new test instance for each test method. You can switch to PER_CLASS with @TestInstance(TestInstance.Lifecycle.PER_CLASS), where a single test instance is shared across the class's methods.

The ApplicationContext is normally cached and reused by Spring TestContext across tests with equivalent configurations. Thus, a new test instance can receive the exact same singleton bean from the context cache while the test instance itself is a brand-new object.

High-level diagram:

~~~text
JUnit creates TestInstance A
        |
        v
Spring injects beans from ApplicationContext X
        |
        v
Run test method 1
        |
        v
Finish test method 1
        |
        v
JUnit creates TestInstance B (PER_METHOD)
        |
        v
Spring injects beans again from ApplicationContext X
        |
        v
Run test method 2
~~~

In the diagram, TestInstance A and B are different objects, yet ApplicationContext X can be reused. A singleton bean in context X can also be the exact same object across both tests. Therefore, do not let mutable state in a singleton bean make tests depend on execution order.

### Test Fixtures and Singleton Beans

A test fixture typically includes input data, mocks, expected results, and helper variables for a test. Fixtures should be scoped appropriately to the test method and initialized or reset explicitly.

Singleton beans default to one instance per bean definition within an ApplicationContext. When a context is cached, a singleton bean can persist across multiple test classes. If a bean holds lists, counters, or mutable state, tests must ensure that state is reset or isolated.

Do not confuse @Autowired injecting a singleton bean into a test field with that field itself becoming a singleton. A field on a test instance follows the test lifecycle; the object referenced by that field may be a singleton bean managed by the context.

### When Is @DirtiesContext Needed?

@DirtiesContext marks an ApplicationContext as no longer fit for reuse, causing Spring to evict it from the cache and recreate it when needed. It is useful when a test alters the structure or internal state of the context in a way that cannot be cleaned up with regular fixtures.

Do not use @DirtiesContext as a default mechanism to reset all data. When you only need to delete database records, transaction rollback, SQL cleanup, or fake reset methods are usually more appropriate. Recreating the entire context can slow down a test suite significantly.

## 9. TestConfiguration, @Import, and Component Scanning

Tests can assemble a context from multiple configuration sources. @ContextConfiguration lets you specify configuration classes or resources to load. @SpringJUnitConfig is a composed annotation combining SpringExtension and @ContextConfiguration for JUnit Jupiter.

Example using explicit configuration:

~~~java
@SpringJUnitConfig({
        InventoryConfiguration.class,
        InventoryAdditionalTestConfig.class
})
class InventoryIntegrationTest {
    @Autowired
    private InventoryService inventoryService;
}
~~~

The specified configuration classes contribute beans to the same context. With @Import, one configuration can import other configurations or specific bean classes.

In Spring Boot, @SpringBootTest typically loads the main application configuration and creates a broader context. The test instance is still created by JUnit and injected by Spring. @TestConfiguration can add test-only beans without turning the test class into a bean.

Do not include a test class in component scanning just to receive @Autowired. Declare test configuration and let TestContext manage fixture injection. Component scanning is for application classes intended to be registered as beans.

## 10. Common Mistakes When Confusing the Two Kinds of Objects

### Creating @Mock While the Service Still Calls the Real Database

The usual cause is that the mock sits only on a test instance field, while the service was created inside the context with a different repository bean. If you want a unit test, instantiate the service via its constructor. If you want to keep the context, use a bean-override mechanism such as @MockitoBean or a fake bean in test configuration.

### Putting @Component on a Test Class Expecting Spring to Manage It

The test framework already creates the test instance and Spring TestContext has its own injection mechanism. Registering a test class as a component is usually unnecessary and can clutter component scanning or context configuration. Keep the test class as a fixture and register only the application classes to be tested.

### Mutating Singleton Bean State in Tests

A test can mutate a bean's state and cause later tests to fail. Design beans without unnecessary mutable state, reset data between tests, or use a fresh context only when genuinely needed.

### Using @DirtiesContext to Fix All Data Errors

A fresh context is not the optimal way to clean database data. Identify whether data lives in a bean, transaction, or database and use the cleanup mechanism with the right scope.

### Assuming an @Autowired Test Field Means the Test Object Is a Bean

@Autowired only expresses an injection request. It does not decide who creates the test instance and does not register the test class in the ApplicationContext.

### Confusing @TestConfiguration with the Test Instance

@TestConfiguration is a configuration class contributing beans to the context. The test class using that configuration remains a separate object managed by JUnit. A @Bean method in configuration may return a bean used in the test, yet the test instance itself is not created by that method.

## 11. Workflow for Choosing How to Create Objects in Tests

When writing Spring tests, determine the scope to verify first:

1. If you need to test the logic of a Java class, instantiate the object via its constructor and pass simple real dependencies, fakes, or Mockito mocks. No ApplicationContext is needed.
2. If you need to test Spring wiring or bean lifecycles, use @SpringJUnitConfig or @ContextConfiguration to create a bounded context.
3. If you need to test full Spring Boot application configuration, use @SpringBootTest when the benefit of a complete context is required.
4. If you want a service in the context to use a mock of a dependency, use @MockitoBean on a supported Spring Framework version or configure a replacement fake bean.
5. If you want the test fixture to receive beans from the context, use @Autowired or constructor/method parameter injection via SpringExtension.
6. If a test alters singleton bean or context state, identify an appropriate reset mechanism; use @DirtiesContext only when the context must be discarded.
7. Keep each test's fixture data isolated and avoid letting shared state make results depend on execution order.

Distinguishing clearly between the test instance and beans helps you pick the right mechanism for each need. The test instance is where JUnit runs checks and Spring can inject fixtures; beans are components Spring manages in the ApplicationContext. @Mock acts on the fixture, while @MockitoBean and @Bean act on the bean graph. Understanding that boundary keeps dependencies, lifecycles, and object state under control.
