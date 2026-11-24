# Context Layer Names and Merge or Override Rules

In the Spring TestContext Framework, a test can load an ApplicationContext from multiple configuration classes or multiple resources. When a test class extends another test class, context configuration can also be inherited, merged, or replaced. In multi-layered web applications, one context can act as the parent of another. Without a clear understanding of these rules, tests easily load too many beans, miss configurations, create unexpected new contexts, or unintentionally retain configuration from a parent class.

Spring provides **@ContextConfiguration** to declare configuration sources and **@ContextHierarchy** to describe multi-layered relationships. The **name** attribute of each @ContextConfiguration identifies a layer within the hierarchy. Attributes such as **inheritLocations** and **inheritInitializers** control whether configuration from the superclass is inherited or replaced. These rules must be distinguished from bean definition overriding or selecting a bean when multiple candidates exist.

This lesson focuses on naming context layers, how Spring merges or replaces configuration metadata across test inheritance hierarchies, parent-child relationships between ApplicationContexts, and how to design predictable test hierarchies.

## 1. ApplicationContext in Spring TestContext

ApplicationContext is the container that manages beans, dependency injection, events, and core Spring services. In testing, the Spring TestContext Framework creates and manages the context based on test class metadata.

Configuration sources can come from:

- Java classes annotated with @Configuration.
- Classes declared in the classes attribute of @ContextConfiguration.
- XML resources declared in locations.
- ApplicationContextInitializer implementations registered to customize the context before refresh.
- Additional configurations provided by tests or the framework.

Example of a test class using Java configuration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
class OrderServiceTest {
    @Autowired
    OrderService orderService;
}
~~~

SpringExtension connects JUnit Jupiter with the TestContext Framework. @ContextConfiguration declares OrderTestConfig as the configuration source used to build the context. Spring loads the context before running tests and injects the required dependencies into the test instance.

Another test class with the same configuration metadata can reuse the cached context. Thus, configuration metadata not only determines which beans are loaded, but also affects whether contexts can be shared across tests.

### 1.1. Context Configuration Is Metadata, Not a Bean

Values of classes, locations, initializers, profiles, and properties describe how to create the context. They are neither bean names nor bean instances.

For example:

- OrderTestConfig is a configuration class.
- orderService is a bean name that can be registered in the context.
- "web" can be the name of a layer in @ContextHierarchy.

These three concepts serve different purposes. Naming a context layer "web" does not create a bean named "web". Likewise, two contexts both having a bean named orderService does not mean they are the same context or the same instance.

## 2. @ContextConfiguration and Inheritance Rules

@ContextConfiguration declares configuration sources for a context. Common attributes include:

| Attribute | Role |
| --- | --- |
| classes | Configuration or component classes to load |
| locations / value | Paths to configuration resources, typically XML |
| initializers | ApplicationContextInitializer implementations |
| inheritLocations | Allows inheriting and merging locations/classes from the parent test class |
| inheritInitializers | Allows inheriting initializers from the parent test class |
| name | Names a layer when used in a context hierarchy |
| loader | Selects the ContextLoader that creates the context |

With inherited test classes, **inheritLocations = true** by default. When a subclass declares an additional @ContextConfiguration, the subclass's classes or locations are merged with the configuration inherited from the parent class.

Example:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = BaseTestConfig.class)
abstract class BaseServiceTest {
}

@ContextConfiguration(classes = PaymentTestConfig.class)
class PaymentServiceTest extends BaseServiceTest {
}
~~~

With default inheritance configuration, Spring uses both BaseTestConfig and PaymentTestConfig to build the context for PaymentServiceTest. Merging here means merging configuration sources, not merging two existing ApplicationContexts into a single object.

### 2.1. Merging Parent and Child Class Configurations

When inheritLocations is true, configuration sources declared on the subclass are appended to the inherited configuration sources. This is useful when the superclass supplies foundational beans shared across multiple test groups, while the subclass adds only specialized beans.

Example:

~~~java
@Configuration
class SharedTestConfig {
    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}

@Configuration
class BillingTestConfig {
    @Bean
    BillingPolicy billingPolicy() {
        return new BillingPolicy();
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
abstract class SharedServiceTest {
}

@ContextConfiguration(classes = BillingTestConfig.class)
class BillingServiceTest extends SharedServiceTest {
}
~~~

BillingServiceTest receives both testClock and billingPolicy provided both configurations register without bean definition conflicts. The parent class can supply shared components such as clocks, converters, fixture adapters, or basic test settings.

### 2.2. Replacing Inherited Configuration Sources

If the subclass does not want to use the parent class's locations/classes, set **inheritLocations = false**:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = LegacyBaseConfig.class)
abstract class LegacyBaseTest {
}

@ContextConfiguration(
    classes = IsolatedPaymentConfig.class,
    inheritLocations = false
)
class IsolatedPaymentTest extends LegacyBaseTest {
}
~~~

In this case, IsolatedPaymentConfig replaces the inherited configuration sources for the subclass's context. It does not automatically load LegacyBaseConfig.

This is a useful option when the superclass holds default configuration unsuitable for a specialized test group. However, check whether the subclass still needs any foundational beans from the superclass. If so, import them intentionally into the new configuration.

### 2.3. inheritInitializers Is a Separate Rule

inheritLocations and inheritInitializers govern two different kinds of metadata:

- inheritLocations controls inheritance of locations/classes.
- inheritInitializers controls inheritance of ApplicationContextInitializers.

By default, initializers are inherited. If a subclass sets inheritInitializers = false, initializers from the parent class are not inherited into that configuration.

Do not assume inheritLocations = false automatically removes initializers as well. If you need to replace both configuration sources and initializers, set each attribute explicitly according to your goal.

## 3. Why Name Context Layers?

A traditional web application can have multiple ApplicationContexts:

- A root context containing services, repositories, transaction managers, and shared beans.
- A web context containing controllers, MVC configuration, view resolvers, and web-specific components.
- Some applications also have separate contexts per DispatcherServlet or per independent web module.

These contexts form a hierarchy: a child context can access beans from its parent context, whereas the parent context cannot see beans that exist only in the child context.

When a test class inherits a hierarchy, Spring needs to know which layer the subclass's declared configuration belongs to. The **name** attribute of @ContextConfiguration identifies each layer so configurations merge into the right level.

Example:

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
abstract class BaseWebTest {
}
~~~

Here the hierarchy has two layers ordered top to bottom:

1. root: the root context, using RootConfig.
2. web: the child context of root, using BaseWebConfig.

The names "root" and "web" are layer identifiers in test metadata. They are not bean names, profile names, or URL names.

### 3.1. Layer Ordering in @ContextHierarchy

@ContextConfiguration entries in @ContextHierarchy are declared in parent-to-child order. The first configuration creates the parent context; the next configuration creates a child context using the previous context as its parent.

Example:

~~~text
Root ApplicationContext
  - service
  - repository
  - transaction manager
        |
        v
Web ApplicationContext
  - controller
  - handler mapping
  - view resolver
~~~

Beans in the Web ApplicationContext can use beans from the Root ApplicationContext. Beans registered only in the Web ApplicationContext do not automatically appear when querying the Root ApplicationContext.

Do not invert the order just to make one bean easier to reach. Describe the hierarchy according to the application's actual boundaries.

### 3.2. Layer Names vs. Layer Indices

Spring must distinguish levels when comparing hierarchy configurations between parent and child classes. If no explicit name is provided, the framework can use default names based on each level's position in the hierarchy.

For a simple hierarchy with no complex inheritance, default names may suffice. However, when a subclass adds to or replaces a specific layer, explicit names like "root", "web", and "adminWeb" make intent clearer and reduce the risk of merging into the wrong level.

Use stable, meaningful names consistently across test classes. Avoid arbitrarily changing names in subclasses because layer identification by name affects how Spring inherits, merges, or replaces metadata.

## 4. Merging Configuration at the Same Hierarchy Layer

When a child test class declares @ContextHierarchy, Spring determines which layer of the inherited hierarchy the new configuration belongs to. If the layer name matches a layer in the superclass, the configuration can be merged into that exact layer according to @ContextConfiguration inheritance rules.

Parent class example:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = CommonWebConfig.class
    )
})
abstract class BaseWebTest {
}
~~~

Subclass adding web configuration:

~~~java
@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = AdminWebConfig.class
    )
})
class AdminControllerTest extends BaseWebTest {
}
~~~

The name "web" on the subclass matches the "web" layer of the parent class. With the default inheritLocations of true, AdminWebConfig is merged with CommonWebConfig at the web layer. The root layer is inherited from the parent class.

Expected structural result:

~~~text
root
  RootConfig
    |
    v
web
  CommonWebConfig
  AdminWebConfig
~~~

This example assumes the configurations can coexist. If they register beans with duplicate names or multiple beans of the same type without a resolution rule, the context may fail or injection may become ambiguous. Merging metadata does not automatically resolve bean conflicts.

### 4.1. Different Names Can Create a Different Layer

If a subclass declares a different name from the layer it wants to extend, Spring cannot infer they are the same level based on what the author considers similar meaning. A new name can be treated as a different configuration level in the inherited metadata.

For example, if the parent class names the web layer "web" while the subclass names it "mvc" intending to add configuration to the web layer, the two names do not match. Do not rely on both containing "web" or both using WebConfig expecting the framework to merge them automatically.

When you want to merge, use the exact same layer name. When you want to create a new level, use a new name and declare the parent-child position properly in the hierarchy.

### 4.2. Merging Does Not Mean Bean Overriding

Suppose CommonWebConfig and AdminWebConfig both declare a bean named "menuService". Merging both configuration classes into the web layer does not mean Spring automatically combines both objects into one or always chooses the subclass's bean.

Registering beans with duplicate names depends on how bean definitions are registered and the context's overriding policy. If multiple beans share a type under different names, autowiring may require @Primary, @Qualifier, or another explicit disambiguation mechanism.

Distinguish between:

- **Merging context metadata:** combining configuration class/resource lists for the same context level.
- **Bean definition overriding:** one bean definition replacing another with the same name in a registry, if allowed by current mechanisms and policies.
- **Dependency candidate resolution:** Spring choosing the appropriate bean to inject when one or more candidates exist.

These three concepts are related, yet they are not the same operation.

## 5. Overriding a Layer's Configuration While Keeping the Parent Layer

Sometimes a subclass wants to keep the Root ApplicationContext while completely replacing the Web ApplicationContext configuration. In that case, match the layer name and set inheritLocations = false on that layer's configuration.

Example:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = CommonWebConfig.class
    )
})
abstract class BaseWebTest {
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = IsolatedAdminWebConfig.class,
        inheritLocations = false
    )
})
class IsolatedAdminControllerTest extends BaseWebTest {
}
~~~

Meaning:

- The root layer remains inherited.
- The web layer remains the layer being configured.
- IsolatedAdminWebConfig replaces the inherited web configuration sources.
- CommonWebConfig is not merged into the subclass's web layer via this configuration.

Diagram:

~~~text
root
  RootConfig
    |
    v
web
  IsolatedAdminWebConfig
~~~

The key point is that inheritLocations = false applies to the configuration metadata of the corresponding level. It does not remove beans from another parent context, does not alter the source code of configuration classes, and does not automatically remove beans indirectly imported by the new configuration.

### 5.1. When Should You Replace Instead of Merge?

Merging fits when the subclass genuinely needs to add beans to the shared configuration. Overriding fits when the inherited configuration is incompatible or when the test needs an isolated context.

Examples:

| Scenario | Choice |
| --- | --- |
| Parent provides Clock, child adds BillingService | Merge |
| Parent provides default database config, child needs a completely different test database | Override or use dedicated test configuration |
| Parent loads shared MVC config, child adds dedicated controller/configuration | Merge if no conflicts exist |
| Parent loads real beans, child needs an isolated config to test a failure path | Intentional override |
| Child only wants to swap one collaborator bean | Consider bean override/test configuration instead of replacing all locations/classes |

Do not use inheritLocations = false as an arbitrary way to wipe a context. It can drop foundational configurations that the test still needs.

## 6. Context Layer Names Are Not Bean Names

A common source of confusion is the word "name" appearing across several APIs:

| Name | Where Used | Meaning |
| --- | --- | --- |
| Context hierarchy level name | @ContextConfiguration(name = "...") | Identifies a layer in TestContext's hierarchy |
| Bean name | @Bean("..."), @Component("...") | Identifies a bean in the BeanFactory |
| Profile name | @ActiveProfiles("...") | Selects configuration groups by profile |
| Property key | @TestPropertySource(properties = "...") | Supplies configuration values |
| Context display/id in logging | Framework/runtime | Used for identifying or diagnosing contexts |

Example:

~~~java
@Configuration
class RootConfig {
    @Bean("orderService")
    OrderService orderService() {
        return new OrderService();
    }
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
class OrderWebTest {
}
~~~

"root" is the level name in the test hierarchy. "orderService" is the bean name in the Root ApplicationContext. Renaming the level does not rename the bean; renaming the bean does not change how Spring merges configuration levels.

## 7. Parent-Child Rules and Bean Visibility

A context hierarchy creates a real parent-child relationship between ApplicationContexts.

### 7.1. Child Contexts See Parent Context Beans

If the root context has OrderService and the web context has OrderController, OrderController can inject OrderService from the parent context:

~~~text
Root context
  orderService
  orderRepository
  transactionManager
       |
       v
Web context
  orderController
  mvcHandlerMapping
~~~

Beans in the child context are searched in the child context first, and then Spring can search upward in the parent when needed. Thus, controllers in the web context can use services in the root context.

### 7.2. Parent Contexts Do Not See Child Context Beans

Visibility is asymmetric. The root context cannot inject beans registered only in the web context. If a service in root needs to depend on a controller in child, that is usually a sign of inverted layering.

Keep dependencies flowing in this direction:

~~~text
Web layer -> Application/Service layer -> Persistence/Infrastructure ports
~~~

The context hierarchy should reflect that dependency direction.

### 7.3. Same-Named Beans in Parent and Child

If both parent and child define a bean with the same name, the child bean can shadow the parent bean when looking up from the child context. This does not delete the bean definition from the parent context. A direct query on the parent still sees the parent's bean.

This differs from registering two beans with the same name into the same BeanFactory. In the latter case, bean definition overriding policies and registration rules decide whether replacement is allowed or raises an error.

If shadowing is intentional, document it clearly in the test configuration and verify the bean injected into the right context. Otherwise, pick distinct names or use @Qualifier/@Primary to express dependency selection explicitly.

## 8. Merging Configuration Sources and Bean Conflicts

When multiple configuration classes are loaded into one context, Spring processes bean definitions according to bean registration rules. Several situations can occur:

### 8.1. Two Beans with Different Names, Same Type

Example:

~~~java
@Configuration
class PaymentConfig {
    @Bean
    PaymentGateway primaryGateway() {
        return new PrimaryPaymentGateway();
    }

    @Bean
    PaymentGateway fallbackGateway() {
        return new FallbackPaymentGateway();
    }
}
~~~

Two beans of the same type do not necessarily conflict during registration, yet type-based injection can be ambiguous without a selection rule. You can use @Primary or @Qualifier depending on the contract.

~~~java
@Bean
@Primary
PaymentGateway primaryGateway() {
    return new PrimaryPaymentGateway();
}
~~~

@Primary does not override the bean definition of fallbackGateway. It simply marks the preferred candidate when Spring needs to pick a matching bean during certain injection types.

### 8.2. Two Beans with the Same Name

If two configurations register beans with the same name in a single BeanFactory, behavior depends on the bean definition overriding policy and how configurations are loaded. Some environments allow a later bean definition to replace an earlier one; some setups, especially in Spring Boot, reject overriding and fail context initialization.

Therefore, do not rely on configuration load order to silently replace beans. Choose one of these explicit options:

- Import only the configuration containing the desired bean.
- Use @Profile or @Conditional to select configurations.
- Use @Primary or @Qualifier when multiple valid beans share a type.
- Use test bean-override mechanisms when the goal is replacing a collaborator in the context.
- Separate dedicated test configurations instead of loading two conflicting configurations.

### 8.3. Merging Configuration Classes Does Not Mean Merging Methods

If parent and child classes declare two configuration classes, TestContext can merge those two classes as sources to build the context. Spring still processes each bean definition, registration condition, import, and dependency via container mechanisms.

There is no automatic merging of the bodies of two `@Bean` methods sharing a name into one bean. One bean definition is a single registration unit; duplicate names must be handled according to container policies.

## 9. Inheriting Initializers and Other Test Configurations

Beyond locations/classes, TestContext has other metadata sources. Be aware that they follow their own rules.

### 9.1. ApplicationContextInitializer

Initializers run before the context is refreshed and can register property sources, bean definitions, or customize the context. When a child test class inherits configuration, initializers are also inherited by default if inheritInitializers is true.

Example:

~~~java
class SharedTestInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context) {
        TestPropertyValues.of(
            "feature.enabled=false"
        ).applyTo(context);
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SharedTestConfig.class,
    initializers = SharedTestInitializer.class
)
abstract class BaseFeatureTest {
}
~~~

Subclasses can add initializers. If you do not want to inherit the parent class's initializers, set inheritInitializers = false on the corresponding @ContextConfiguration.

### 9.2. @ActiveProfiles

Active profiles are metadata selecting profiles for TestContext. They are not hierarchy level names. When tests inherit, profiles have their own inheritance and merging rules; the inheritProfiles attribute can be used to control profile inheritance.

Do not use inheritLocations to change profiles. If a subclass needs different profiles, configure @ActiveProfiles purposefully and verify profile inheritance policy independently.

### 9.3. @TestPropertySource

@TestPropertySource supplies properties to the test context's Environment. It has its own inheritance and precedence mechanisms. Replacing locations/classes in @ContextConfiguration does not mean all inherited property sources are discarded as well.

When a test needs to change one configuration value, consider declaring the property directly rather than replacing the entire context configuration. This limits the change to the exact metadata needing adjustment.

### 9.4. Bean Overrides for Tests

Some Spring Test versions provide annotations to replace beans in the context with mocks or test beans. This is a bean-override mechanism, distinct from replacing all locations/classes of the context.

If you only want to swap PaymentGateway in one test, you do not necessarily have to set inheritLocations = false and recreate the entire root/web configuration. Use the bean-override mechanism supported by your project's Spring version or register an intentional test configuration.

## 10. Context Caching and the Impact of Configuration

The Spring TestContext Framework caches ApplicationContexts for reuse across tests with the same configuration. Caching makes suites run faster because the context does not need to be recreated for every test method.

The cache key is built from configuration metadata such as:

- Context locations and classes.
- Context initializer classes.
- Active profiles.
- Property source descriptors and inline properties.
- Context customizers.
- Context loader.
- Parent context in the hierarchy.
- Other related attributes of the test context.

Therefore, two nearly identical test classes with minor metadata differences can still create separate context cache entries. Conversely, tests with identical configuration can share a context.

### 10.1. Layer Names Affect Hierarchy Merging

In a context hierarchy, level names help Spring match corresponding configurations between parent and child classes. If you rename a level without updating subclasses, metadata may no longer merge as expected.

Treat level names as part of the test configuration contract. Choose meaningful, stable names and reuse them consistently.

### 10.2. Do Not Use @DirtiesContext to Fix Broken Configuration

@DirtiesContext marks a context for eviction from the cache after a test or test class. It is useful when a test alters singleton or context state in a way that cannot be restored safely.

It is not a fix for bean definition conflicts, mismatched hierarchy level names, or incorrect metadata inheritance. Those problems must be fixed in configuration.

With context hierarchies, Spring supports modes to close contexts at the current level or across the entire hierarchy. Choose the appropriate mode when a test genuinely corrupts one level or related levels. Do not use @DirtiesContext broadly when you only need to roll back database data or reset fakes.

## 11. Complete Example: Root Context and Web Context

Suppose a Spring MVC application has shared services in the root context and controllers in the web context.

Root configuration:

~~~java
@Configuration
class RootConfig {

    @Bean
    OrderService orderService() {
        return new OrderService();
    }
}
~~~

Web configuration:

~~~java
@Configuration
@EnableWebMvc
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

Test base:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
abstract class BaseOrderWebTest {
}
~~~

Test class:

~~~java
class OrderControllerContextTest extends BaseOrderWebTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    @Test
    void web_context_can_resolve_service_from_parent() {
        assertThat(webApplicationContext.getBean(OrderController.class))
            .isNotNull();
        assertThat(webApplicationContext.getBean(OrderService.class))
            .isNotNull();
    }
}
~~~

The example above illustrates how the web context sees services from the root context. In a real application, the root context is typically the parent context initialized first, and the web context is the child.

### 11.1. Adding Web Configuration for a Group of Tests

~~~java
@Configuration
class AdminWebTestConfig {
    @Bean
    AdminController adminController(OrderService orderService) {
        return new AdminController(orderService);
    }
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = AdminWebTestConfig.class
    )
})
class AdminControllerContextTest extends BaseOrderWebTest {
}
~~~

Because the name "web" matches the level in the parent class and inheritLocations defaults to true, the admin configuration is merged with the inherited web configuration. The root level remains inherited.

### 11.2. Replacing Web Configuration for an Isolated Test

~~~java
@Configuration
class IsolatedWebTestConfig {
    @Bean
    IsolatedController isolatedController() {
        return new IsolatedController();
    }
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = IsolatedWebTestConfig.class,
        inheritLocations = false
    )
})
class IsolatedControllerTest extends BaseOrderWebTest {
}
~~~

This test keeps the root context from the parent class while replacing the web configuration sources with IsolatedWebTestConfig. If the isolated web configuration still needs MVC infrastructure or other beans, they must be declared or imported explicitly.

## 12. Common Mistakes

### Changing Level Names Between Parent and Child Classes

Parent uses "web", child uses "mvc" while expecting Spring to merge both configurations into the same level. Use the exact same name if you want to merge/override an existing level.

### Using inheritLocations = false and Accidentally Dropping Needed Configuration

This attribute replaces inherited configuration sources at the corresponding level. If the subclass still needs beans from the parent configuration, import or redeclare them explicitly.

### Assuming Merging Metadata Resolves Duplicate Bean Names

Loading two configuration classes together does not mean beans with the same name merge automatically. Check bean definition overriding, @Primary, @Qualifier, or separate configurations.

### Confusing Context Level Names with Bean Names

Level names serve hierarchy metadata; bean names serve the BeanFactory. Changing one does not automatically change the other.

### Ordering Parent and Child Incorrectly

The first context is the parent, and subsequent contexts are children in declaration order. Reversing the order can break bean visibility and dependency direction.

### Creating Unnecessary Hierarchies

An application without separate root/web contexts does not necessarily need @ContextHierarchy. Adding levels increases the number of contexts to initialize and makes configuration harder to understand.

### Using @DirtiesContext to Dodge Metadata Errors

Cache eviction does not fix level names or inheritance rules. Fix the configuration source first.

### Accidentally Creating Many Near-Identical Contexts

Minor differences in classes, profiles, or properties create separate cache entries. Reuse shared configurations and only split contexts when test goals genuinely differ.

## 13. Workflow for Designing a Context Hierarchy

When building a test group with inheritance, follow this sequence:

**Step 1 – Identify application boundaries.** Separate shared beans, web-specific beans, and module-specific beans.

**Step 2 – Decide if multiple contexts are needed.** If a single ApplicationContext suffices, use @ContextConfiguration or the corresponding composed annotation.

**Step 3 – Sketch the parent-child order.** Which layer holds services/repositories? Which layer holds controllers and MVC infrastructure?

**Step 4 – Assign stable level names.** Use clear names like root, web, or adminWeb consistently across inherited classes.

**Step 5 – Define parent class configuration.** Put genuinely shared configurations into the base test.

**Step 6 – Choose merge or replace for subclasses.** Use the same name with default inheritLocations to augment; use the same name with inheritLocations = false to replace configuration sources at that level.

**Step 7 – Control initializers and other metadata.** Review inheritInitializers, active profiles, test properties, and bean overrides separately.

**Step 8 – Check bean visibility and conflicts.** Confirm child sees parent, parent does not depend on child, and duplicate names/types are handled explicitly.

**Step 9 – Watch the context cache.** Avoid creating unnecessary configuration variants and use @DirtiesContext only when the context genuinely cannot be reused.

**Step 10 – Verify actual behavior.** Do not stop at context startup; send requests or invoke beans to verify the behavior the test must prove.

## 14. Quick Reference Table

| Need | Configuration to Check |
| --- | --- |
| Add configuration classes to a child test class | @ContextConfiguration with default inheritLocations |
| Replace parent classes/locations in a single context | inheritLocations = false |
| Add initializers from a child class | initializers and inheritInitializers |
| Do not inherit parent initializers | inheritInitializers = false |
| Declare multiple parent-child contexts | @ContextHierarchy |
| Identify matching level between parent and child | @ContextConfiguration(name = "...") |
| Merge configuration into an existing level | Same name, default inheritLocations |
| Replace configuration of an existing level | Same name, inheritLocations = false |
| Choose a bean when multiple beans share a type | @Primary or @Qualifier |
| Swap a single bean for tests | Bean-override mechanism or test configuration |
| Evict context from cache after test | @DirtiesContext when genuinely needed |

## Conclusion

Context layer names help the Spring TestContext Framework identify the right level in a hierarchy when test classes inherit or extend configuration. @ContextHierarchy describes ApplicationContexts in parent-child order; @ContextConfiguration(name = "...") assigns stable names to each level. When names match, child configurations can merge into the corresponding level under default inheritance rules. Setting inheritLocations = false replaces inherited classes/locations at that level.

Distinguish merging configuration metadata from bean definition overriding and dependency resolution. Loading two configuration classes together does not automatically determine which bean wins on name or type collisions. Designing clear level names, parent-child direction, merge/replace policies, and bean selection makes contexts predictable, improves cache utilization, and keeps test hierarchies maintainable.
