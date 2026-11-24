# @ContextHierarchy for Parent-Child Relationships

The Spring TestContext Framework can create a single ApplicationContext for a test, yet some applications have a multi-layered context structure. For example, a root context contains services, repositories, and shared infrastructure; a child context contains controllers, handlers, or beans belonging only to a web module. In that structure, the child context needs to use beans from the parent context, while the parent context should not depend back on beans that exist only in the child context.

**@ContextHierarchy** allows declaring a chain of ApplicationContexts in a parent-child relationship for Spring tests. Each level in the chain is described by a **@ContextConfiguration**. The Spring TestContext Framework loads the levels in order, establishes the parent-child relationship, and provides the final-level context to the test.

This lesson covers how to declare a hierarchy using Java or XML, how beans are resolved across levels, how to share configuration across inherited test classes, and how to manage caching and the lifecycle of the hierarchy.

## 1. Why Do We Need Parent-Child Relationships Between ApplicationContexts?

A Spring application can organize beans across multiple scopes. In a traditional web application, a familiar structure is:

- **Root context**: services, repositories, transaction managers, data sources, business components, and shared beans.
- **Web context**: controllers, MVC configuration, view resolvers, handler interceptors, and beans serving only the web layer.

The web context needs to call services in the root context. However, services and repositories do not need to know which controller is using them. Splitting into two contexts keeps dependency boundaries clearer.

A general structure can be illustrated as follows:

~~~text
Parent ApplicationContext
    |
    +-- OrderRepository
    +-- PaymentGateway
    +-- OrderService
    +-- TransactionManager
          |
          v
Child ApplicationContext
    |
    +-- OrderController
    +-- WebExceptionHandler
    +-- WebConfiguration
~~~

The child context can look up beans from the parent context. The parent context cannot look up beans registered only in the child context. This relationship lets upper layers consume services from lower layers in a one-way dependency direction.

In tests, when you need to verify that multiple context layers work together properly, you can declare a hierarchy using **@ContextHierarchy** instead of merging all configurations into a single ApplicationContext.

## 2. How Does @ContextHierarchy Work?

**@ContextHierarchy** is an annotation in the Spring TestContext Framework. It accepts an array of **@ContextConfiguration** annotations. Each element describes the configuration of one context level in the hierarchy.

Minimal example:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(classes = RootConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
class OrderWebContextTest {
}
~~~

Spring creates two contexts:

1. The first context from RootConfig. This is the parent context.
2. The second context from WebConfig. This is the child context and has its parent set to the first context.

The order of elements in **@ContextHierarchy** matters: the first configuration is the top-level parent, and each subsequent configuration is a child of the one immediately preceding it.

If three elements are declared, the second context is a child of the first, and the third context is a child of the second. Thus, a hierarchy can have more than two levels when the architecture genuinely requires it.

### Each Level Has Its Own Configuration

Each **@ContextConfiguration** can specify Java configuration classes, XML resources, initializers, or an appropriate context loader. Example:

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = InfrastructureConfig.class),
    @ContextConfiguration(classes = ApplicationConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
~~~

In this example, the three contexts represent infrastructure, application, and web layers respectively. Beans at a child level can use beans at parent levels above them through Spring's bean resolution mechanism.

**@ContextHierarchy** is not a shorthand for putting multiple configuration classes into the same context. It instructs Spring to create multiple ApplicationContexts in a parent-child relationship. If you only want to register multiple configurations into a single context, pass multiple classes in the classes attribute of **@ContextConfiguration**, or use **@Import**.

## 3. Bean Lookup Rules Between Parent and Child Contexts

The parent-child relationship of ApplicationContext relies on bean lookup through the parent BeanFactory.

- The child context first searches for beans within its own scope.
- If no matching bean is found at the child level, it can continue searching in the parent context.
- Lookups can continue up through higher parent levels.
- A parent context cannot reach down to retrieve beans registered exclusively in a child context.

For example, RootConfig declares services:

~~~java
@Configuration
class RootConfig {

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}
~~~

WebConfig declares a controller needing OrderService:

~~~java
@Configuration
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

When Spring instantiates OrderController in the child context, it can resolve the OrderService parameter from the parent context. Therefore, the controller can use the service even though the service is not re-registered in WebConfig.

### Beans with the Same Name in the Child Context

If both the parent context and child context have beans with the same name, the child context can define its own bean with that name. When looking up from the child context, the child-level bean takes precedence; the parent bean still exists in the parent context.

This can be useful when a test wants to swap a collaborator at the child layer. However, shadowing a parent bean should be done intentionally because it can make it hard for readers to tell which bean is being used.

Do not rely on name collisions to swap beans implicitly if the project configuration can use a clearer mechanism such as profiles, test configuration, or bean overrides.

### Why Not Put All Beans in the Parent Context?

If controllers are placed in the root context, child contexts may unintentionally receive unnecessary web beans. That blurs architectural boundaries and can cause errors when an application has multiple web contexts or multiple DispatcherServlets.

Place beans at the lowest level in the hierarchy required by all their consumers. Shared beans belong in the parent context; module-specific beans belong in the corresponding child context.

## 4. Example of Parent-Child Configuration in Java

Suppose an application has OrderService using a repository, and OrderController using OrderService. We want to test the wiring of the two context layers.

Parent configuration:

~~~java
@Configuration
class RootConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

Child configuration:

~~~java
@Configuration
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

Test declaring the hierarchy:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class OrderControllerContextTest {

    @Autowired
    private OrderController orderController;

    @Test
    void createsControllerWithServiceFromParentContext() {
        assertNotNull(orderController);

        OrderView view = orderController.find("order-18");

        assertEquals("order-18", view.id());
    }
}
~~~

Spring loads RootConfig first, then creates the child context from WebConfig with the parent context already in place. OrderController is created in the child context, while OrderService and OrderRepository come from the parent context.

The test injects OrderController from the final context of the hierarchy. Calling the controller in this example illustrates wiring; in a web application, if you want to test HTTP mappings, requests, and responses, use appropriate web configuration with MockMvc or a dedicated web test.

## 5. Configuring a Hierarchy with XML

If the application uses XML, each level can specify one or more resources.

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        locations = "classpath:root-context.xml"
    ),
    @ContextConfiguration(
        name = "web",
        locations = "classpath:web-context.xml"
    )
})
class LegacyWebContextTest {
}
~~~

Example root-context.xml:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderRepository"
          class="example.persistence.InMemoryOrderRepository"/>

    <bean id="orderService"
          class="example.order.OrderService">
        <constructor-arg ref="orderRepository"/>
    </bean>
</beans>
~~~

Example web-context.xml:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderController"
          class="example.web.OrderController">
        <constructor-arg ref="orderService"/>
    </bean>
</beans>
~~~

The orderService bean is declared in the root context. When Spring creates the orderController bean in the child context, the reference to orderService can be resolved through the parent BeanFactory.

XML resources must be on the test runtime classpath. If a resource is not found, the context will fail to initialize. Place files in the test resources directory matching your project's build layout.

## 6. Combining a Context Hierarchy with Web Configuration

In a Spring MVC application, a common pattern is for the root context to hold services and persistence, while the web context holds controllers and MVC infrastructure.

A test can use **@WebAppConfiguration** to instruct Spring to create a WebApplicationContext and provide a mock Servlet environment for web tests. Declaration example:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebMvcConfig.class
    )
})
class OrderWebApplicationContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;
}
~~~

In actual configuration, WebMvcConfig declares or imports the necessary MVC components. RootConfig contains shared services and repositories.

If you want to test HTTP requests through Spring MVC, you can build MockMvc from the WebApplicationContext:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebMvcConfig.class
    )
})
class OrderMvcHierarchyTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void returnsOrderFromParentService() throws Exception {
        mockMvc.perform(get("/orders/order-18"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("order-18"));
    }
}
~~~

This is a configuration pattern for Spring MVC TestContext. The test needs controllers and web components registered in the web context; services and repositories must exist in the root context. Specific imports, beans, and test data depend on the application.

**@WebAppConfiguration** sets up the web environment for TestContext. It does not automatically create the entire MVC configuration, does not automatically register controllers, and does not start a real HTTP server. If you need to verify a server starting and handling requests over a network port, use an integration test style suited to the application.

## 7. Using Multiple Context Levels in a Hierarchy

A hierarchy is not limited to root and web. An application might need three or more levels, though it should only be split when each level has a clear bean scope and dependency relationship.

Example:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "infrastructure",
        classes = InfrastructureConfig.class
    ),
    @ContextConfiguration(
        name = "application",
        classes = ApplicationConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
class FullModuleHierarchyTest {
}
~~~

In this model:

- InfrastructureConfig contains DataSource, repository adapters, clocks, or technical beans.
- ApplicationConfig contains business services and use cases.
- WebConfig contains controllers, MVC configuration, and web-specific components.

The application-level context can use beans from infrastructure. The web-level context can use beans from application and infrastructure through the parent chain.

Do not split contexts just to create many layers for aesthetics. Every level increases the number of configurations to manage and can complicate diagnosing startup failures. If beans do not require parent-child boundaries, a single context with multiple configuration classes is usually simpler.

## 8. Inheriting and Merging Hierarchies Between Test Classes

An important benefit of **@ContextHierarchy** is the ability to share configuration across test classes in an inheritance hierarchy.

For example, a base class declares root and web contexts:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = BaseWebConfig.class
    )
})
abstract class BaseWebTests {
}
~~~

A test for the admin page can add configuration at the web level:

~~~java
@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = AdminWebConfig.class
    )
})
class AdminWebTests extends BaseWebTests {
}
~~~

Hierarchies are inherited and merged by default. The **name** attribute of each **@ContextConfiguration** tells Spring which level to merge. In the example, the root level is inherited; the configuration named web on the subclass is merged into the corresponding web level.

This allows multiple test classes to share the root configuration while still adding specific configuration at a child level.

### Why Should You Name Each Level?

When a hierarchy is inherited, level names clearly express which configurations belong to the same logical position. For example:

- root: application-wide shared beans.
- web: MVC configuration.
- admin: configuration dedicated to the admin area.

Names must match consistently across classes that intend to merge at the same level. If names do not match or hierarchies have different structures, merging may not produce what the author expects.

If no names are specified, Spring relies on level positions in the hierarchy to handle inheritance. With structures spanning multiple classes and levels, explicit naming makes things easier to understand.

### When Do You Not Want to Inherit the Hierarchy?

By default, hierarchy configuration can be inherited from a superclass. If a test class needs to define its own hierarchy without inheriting parent configurations, you can configure **inheritLocations = false** on **@ContextHierarchy**:

~~~java
@ContextHierarchy(
    value = {
        @ContextConfiguration(
            name = "root",
            classes = IsolatedRootConfig.class
        ),
        @ContextConfiguration(
            name = "web",
            classes = IsolatedWebConfig.class
        )
    },
    inheritLocations = false
)
class IsolatedWebTests extends BaseWebTests {
}
~~~

This is useful when a subclass needs an independent hierarchy. Use it intentionally because parent configurations are no longer merged by default.

## 9. Context Hierarchies and the TestContext Cache

Creating an ApplicationContext can be expensive because Spring must process bean definitions, instantiate singletons, run post-processors, wire dependencies, and perform initialization steps.

The Spring TestContext Framework has a context cache to reuse contexts across tests with compatible configurations. With a hierarchy, contexts at each level are managed according to their merged configuration and corresponding parent-child relationships.

For example, two test classes with the same root configuration and the same web configuration can share the respective contexts instead of recreating everything each time.

Factors such as configuration classes, resource locations, initializers, active profiles, property sources, context customizers, context loaders, and the parent context can all affect whether a context can be reused.

### Leveraging the Cache

- Share root configuration for tests that genuinely share the same requirements.
- Keep hierarchy names and level order consistent.
- Avoid creating unnecessary property or profile variations.
- Minimize mutating singleton bean state in tests.
- Do not mark a context dirty if you only need to clean up test data.

Caching reduces startup time, yet does not collapse the contexts into a single context. Each level still retains its own bean registry and lifecycle.

### Watch Out for Mutable State

A singleton bean in the parent context can be used by multiple test classes and multiple child contexts. If a test mutates that bean's state without restoring it, other tests may observe leftover state.

For example, a fake repository in the root context stores orders in a Map. If multiple tests share the root context, data from an earlier test can affect a later test. You can solve this by creating isolated test data, cleaning up data after tests, using a repository with proper transactions, or designing independent fixtures.

Do not rely on test execution order to guarantee valid state.

## 10. @DirtiesContext in a Context Hierarchy

**@DirtiesContext** marks an ApplicationContext as no longer fit for reuse. Spring TestContext removes the relevant contexts from the cache and closes them when appropriate.

When a test uses a hierarchy, you must decide the scope of contexts marked dirty. The **hierarchyMode** attribute of **@DirtiesContext** supports two modes:

- **EXHAUSTIVE**: the default mode; removes the current context along with related contexts in the hierarchy exhaustively.
- **CURRENT_LEVEL**: removes only the context at the current level associated with the test.

Example:

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS,
    hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
)
class AdminWebTests extends BaseWebTests {
}
~~~

If only state in the web context was dirtied, CURRENT_LEVEL can preserve the still-valid parent context. If state changes affect the entire hierarchy, evict the related contexts using the appropriate mode.

Do not use **@DirtiesContext** as a way to clean up all test data. It manages the ApplicationContext lifecycle; it does not replace rolling back transactions, deleting database records, stopping containers, or recalling messages sent to a broker.

Evicting a parent context can also require child contexts that depend on it to be recreated. Consider the dependency scope before choosing hierarchyMode.

## 11. Difference Between a Hierarchy and Multiple Configurations in One Context

A common misconception is declaring multiple configuration classes in **@ContextConfiguration** and assuming Spring creates multiple contexts. In reality, multiple configuration classes in a single declaration are normally loaded into the same ApplicationContext.

Compare:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
    RootConfig.class,
    WebConfig.class
})
class SingleContextTest {
}
~~~

In this example, RootConfig and WebConfig both contribute bean definitions to a single context.

Meanwhile:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(classes = RootConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
class ParentChildContextTest {
}
~~~

The second example creates two contexts with a parent-child relationship.

| Need | Suitable Mechanism |
|---|---|
| Multiple configuration classes forming one context | @ContextConfiguration(classes = {...}) |
| Splitting beans into modules without a parent-child relationship | @Import or multiple configuration classes |
| Child context needs beans from a parent context | @ContextHierarchy |
| Multiple test classes inheriting shared context levels | @ContextHierarchy with name |
| Simply replacing one bean in a test context | Test bean-override mechanism or appropriate test configuration |

Only use a hierarchy when the parent-child relationship is part of the structure being tested or reproduced. If you only want to split configuration files for readability, **@Import** is usually enough.

## 12. Common Mistakes When Using @ContextHierarchy

### Placing a Bean at the Wrong Level

If a controller is declared in the root context yet depends on a bean that only exists in the child context, Spring cannot resolve dependencies in the child-to-parent direction. Place the consuming bean at the child level or move the shared dependency up to an appropriate parent level.

### Assuming the Parent Context Sees Child Beans

Lookups go from child to parent. There is no automatic mechanism for a parent to look up beans in a child. If a service needs a collaborator, that collaborator must be registered in the parent context or passed through an appropriate dependency design.

### Duplicate Bean Declarations Causing Accidental Shadowing

A bean in a child can shadow a bean of the same name in the parent when looking up from the child. This can cause confusing behavior if the test does not realize which bean is in use. Name and scope beans intentionally, avoiding unnecessary name collisions.

### Confusing Multiple Configs with Multiple Contexts

Multiple classes in the classes attribute do not create a hierarchy. You must use **@ContextHierarchy** with one **@ContextConfiguration** per level.

### Wrong Level Order

The first level is the top-level parent, followed by children. If reversed, dependencies may fail to resolve because needed beans reside in a child context.

### Unintended Hierarchy Inheritance

If a superclass already declares a hierarchy, subclasses can inherit and merge configurations. Use clear level names and consider **inheritLocations = false** when an independent hierarchy is needed.

### Using @DirtiesContext Too Broadly

Evicting the entire hierarchy can force multiple contexts to reinitialize, slowing down the test suite. Choose the hierarchy mode matching the level actually dirtied.

### Creating a More Complex Hierarchy Than Needed

Every level adds configuration, caching, and diagnostic complexity. If tests do not need to separate parent and child beans, a single simple context is easier to maintain.

## 13. Workflow for Designing a Hierarchy for a Test

When deciding to use **@ContextHierarchy**, define boundaries before writing annotations:

1. Identify which beans are shared across multiple modules or layers.
2. Place shared beans in the parent context.
3. Place module-specific beans in the child context.
4. Trace dependencies flowing from child up to parent.
5. Choose Java configuration, XML, or initializers for each level.
6. Declare the hierarchy in parent-first, child-next order.
7. Use name for levels that need to merge across inherited test classes.
8. Verify that the context injected into the test is the final level matching the behavior to assert.
9. Manage test data and singleton state so tests do not depend on order.
10. Use @DirtiesContext only when the context is genuinely dirtied and choose the appropriate cache eviction scope.

Combined three-level example:

~~~java
@Configuration
class InfrastructureConfig {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-06-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}
~~~

~~~java
@Configuration
class ApplicationConfig {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock clock) {
        return new OrderService(repository, clock);
    }
}
~~~

~~~java
@Configuration
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "infrastructure",
        classes = InfrastructureConfig.class
    ),
    @ContextConfiguration(
        name = "application",
        classes = ApplicationConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
class OrderHierarchyTest {

    @Autowired
    private OrderController orderController;

    @Test
    void wiresWebApplicationToParentServices() {
        assertNotNull(orderController);

        OrderView result = orderController.find("order-18");

        assertEquals("order-18", result.id());
    }
}
~~~

When Spring processes this configuration, OrderRepository and Clock are created at the infrastructure level; OrderService is created at the application level and receives dependencies from its parent; OrderController is created at the web level and receives OrderService from the parent context.

The example illustrates wiring principles. In real projects, repositories, controllers, and test data must be defined according to the application's actual models and contracts.

## 14. When Should and Shouldn't You Use @ContextHierarchy?

Use it when:

- The application genuinely has a root context and one or more child contexts.
- Child contexts need to share infrastructure beans or services from a parent context.
- Tests need to verify wiring and bean resolution across levels.
- Multiple test classes need to share part of a hierarchy and add configuration at a specific level.
- You need to reproduce a setup with multiple DispatcherServlets or web areas having separate contexts.

Do not use it when:

- All beans can coexist in a single ApplicationContext.
- Splitting configuration is only for organizing files or packages.
- Tests only verify pure Java service logic.
- No dependency or lifecycle requirement needs a parent-child relationship.

A good hierarchy reflects real architectural boundaries. It helps tests confirm beans sit at the right level, dependencies resolve in the proper direction, and configuration can be shared across tests. When a hierarchy brings no concrete benefit, a simple ApplicationContext is usually clearer, faster, and easier to maintain.

**@ContextHierarchy** is the tool for describing multiple ApplicationContexts in a parent-child relationship within the Spring TestContext Framework. By declaring each level with **@ContextConfiguration**, placing beans according to usage scope, naming levels when inheritance is needed, and managing the context cache intentionally, tests can faithfully reproduce an application's multi-layered structure while preserving separation between modules.

