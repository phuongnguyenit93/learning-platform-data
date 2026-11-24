# Combining Component Classes, XML, and `@Import`

A Spring application can contain configuration written in Java, classes with stereotypes such as `@Component` or `@Service`, and beans declared in XML files. This often occurs when a system is gradually migrating from XML to Java configuration, when a library provides a prebuilt XML context, or when modules need to compose configuration piece by piece.

Spring does not require all beans to be declared in the same way. An `ApplicationContext` can load bean definitions from classes, component scans, and XML within the same context. The key mechanisms are direct class registration, `@ComponentScan`, `@Import`, and `@ImportResource`. Choosing the right mechanism keeps configuration readable, avoids duplicate package scanning, and reduces errors caused by beans being registered twice or ambiguous dependencies.

## 1. Sources of Bean Definitions in Spring

Before combining multiple configuration styles, distinguish the sources of bean definitions:

| Source | How It Is Declared | When It Fits |
| --- | --- | --- |
| Directly registered component classes | `AnnotationConfigApplicationContext.register(...)` or `@Import` | When the exact classes to include in the context are known |
| Component scanning | `@ComponentScan` or `<context:component-scan>` | When you want Spring to automatically find stereotype classes in packages |
| Java configuration | `@Configuration` and `@Bean` methods | When you want to declare beans in Java, with conditions and module imports |
| XML bean definitions | `<bean>` in XML files, loaded via `@ImportResource` or an XML reader | Integrating legacy configuration or libraries providing XML |
| Importing configuration | `@Import` | Composing Java configurations or component classes by module |

These sources ultimately all contribute bean definitions to the `ApplicationContext`'s `BeanFactory`. When the context is refreshed, Spring instantiates beans according to their dependencies and lifecycles.

The key point is that **direct class registration, package scanning, and importing classes are three distinct ways of selecting configuration sources**. Direct registration fits when the list of classes is known; component scanning fits when packages form the discovery boundary; `@Import` fits when a configuration explicitly composes other modules.

## 2. Registering Component Classes Directly

With `AnnotationConfigApplicationContext`, you can register classes right when creating the context:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

try (var context = new AnnotationConfigApplicationContext(
        AppConfig.class,
        OrderService.class,
        PricingService.class)) {

    OrderService orders = context.getBean(OrderService.class);
}
```

`AppConfig` can be a `@Configuration` class; `OrderService` and `PricingService` can be component classes. Spring processes annotations on the registered classes, creates corresponding bean definitions, and injects dependencies via constructors or matching annotations.

Example component class:

```java
@Service
public class OrderService {

    private final PricingService pricingService;

    public OrderService(PricingService pricingService) {
        this.pricingService = pricingService;
    }
}
```

Direct registration does not require scanning an entire package. This works well for small applications, minimal test contexts, or module configurations where the list of components is explicitly defined.

You can create an empty context, register classes, and refresh afterward:

```java
var context = new AnnotationConfigApplicationContext();
context.register(AppConfig.class, OrderService.class);
context.refresh();

try {
    OrderService service = context.getBean(OrderService.class);
} finally {
    context.close();
}
```

Calling `refresh()` completes context loading and initialization. Before that point, do not assume singleton beans are ready for use.

## 3. Declaring Java Configuration with `@Configuration` and `@Bean`

`@Configuration` marks a class that contains bean configuration. `@Bean` methods return objects managed by Spring:

```java
@Configuration
public class CoreConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    public PricingService pricingService(Clock applicationClock) {
        return new PricingService(applicationClock);
    }
}
```

Spring recognizes `CoreConfig` as a source of bean definitions. Parameters of `@Bean` methods are resolved from the container, so `PricingService` receives the `Clock` bean managed by the context.

A configuration class can import other configurations, declare component scans, or load XML. Modular organization separates persistence, messaging, security, and web into configurations with distinct responsibilities.

`@Configuration` provides full semantics for `@Bean` methods, where calls between `@Bean` methods are handled by the container via proxying in default mode. `@Component` can be used on classes with `@Bean` methods as lite configuration, but if the class serves as a primary configuration, use `@Configuration` to make the intent clear.

## 4. How Component Scanning Finds Classes

Component scanning lets Spring discover classes carrying stereotypes within packages and subpackages. Common annotations include:

- `@Component`: general-purpose component.
- `@Service`: business logic class.
- `@Repository`: data access class, also supporting persistence exception translation when applied appropriately.
- `@Controller` and `@RestController`: web components.
- `@Configuration`: Java configuration class.

Example:

```java
@Configuration
@ComponentScan(basePackages = {
    "com.example.orders.application",
    "com.example.orders.adapter"
})
public class ApplicationConfig {
}
```

Spring scans the specified packages and registers matching components. Limiting packages helps avoid accidentally bringing beans from unrelated modules into the context.

If the application has a standard package structure, you can use marker classes:

```java
@ComponentScan(basePackageClasses = {
    OrderService.class,
    JpaOrderAdapter.class
})
```

`basePackageClasses` avoids hardcoding package names as strings. Spring uses the packages containing those classes as starting points for scanning.

### Component Scanning Is Not the Same as Direct Registration

When registering `OrderService.class`, you instruct Spring to process that exact class. When using `@ComponentScan`, Spring searches for candidates within the package scope according to filters. Therefore:

- Use direct registration when you want an explicit list of components.
- Use scanning when a module follows stereotype conventions and you want new components discovered automatically.
- Use filters when you need to restrict the types of components discovered.

Avoid scanning overly broad packages such as `com.example` if that package also contains test fixtures, experimental configurations, adapters unused at runtime, or modules with conflicting beans.

## 5. `@Import` Composes Java Configuration Classes

`@Import` lets one configuration class bring other configurations into the same context. Example:

```java
@Configuration
@Import({PersistenceConfig.class, MessagingConfig.class})
public class ApplicationConfig {
}
```

`PersistenceConfig` can declare `DataSource`, `EntityManagerFactory`, or repository adapters; `MessagingConfig` can declare producers and consumers. When Spring processes `ApplicationConfig`, the imported configurations also participate in building bean definitions.

Persistence module example:

```java
@Configuration
public class PersistenceConfig {

    @Bean
    public OrderRepository orderRepository(OrderJpaRepository jpaRepository) {
        return new JpaOrderRepositoryAdapter(jpaRepository);
    }
}
```

An application module can compose configurations:

```java
@Configuration
@Import(PersistenceConfig.class)
public class OrderModuleConfig {

    @Bean
    public PlaceOrderService placeOrderService(
            OrderRepository repository,
            PaymentPort paymentPort) {
        return new PlaceOrderService(repository, paymentPort);
    }
}
```

`@Import` is useful when you want to express module-level dependencies in configuration. Instead of scanning a large package, the root class explicitly declares which modules are assembled into the application.

## 6. `@Import` Can Also Bring Component Classes into the Context

`@Import` is not restricted to `@Configuration` classes. Spring supports importing regular component classes. Example:

```java
@Component
public class OrderIdGenerator {
    public OrderId nextId() {
        return OrderId.random();
    }
}
```

A configuration can import that class:

```java
@Configuration
@Import(OrderIdGenerator.class)
public class OrderModuleConfig {
}
```

Spring registers the imported component class as a bean definition. This fits when a configuration module wants to explicitly declare certain components without scanning the entire package containing them.

For a standalone class, you can consider registering it directly on the context. `@Import` is more useful when assembling the class is part of a module's structure and you want to keep that configuration in Java configuration metadata.

## 7. Import Selectors and Registrars

Beyond a static list of classes, `@Import` supports extension points for deciding which configurations to register.

### `ImportSelector`

`ImportSelector` returns the names of classes to import. It fits when the set of configurations is chosen based on metadata or conditions:

```java
public class StorageImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[] {
            S3StorageConfig.class.getName(),
            StorageHealthIndicatorConfig.class.getName()
        };
    }
}
```

Registering the selector:

```java
@Configuration
@Import(StorageImportSelector.class)
public class StorageModuleConfig {
}
```

Spring invokes the selector while parsing configuration and imports the returned classes. If you need to read properties or environment conditions, use appropriate condition mechanisms; do not perform I/O or produce side effects inside a selector.

### `ImportBeanDefinitionRegistrar`

`ImportBeanDefinitionRegistrar` allows programmatic registration of bean definitions when lower-level control over bean names, constructor arguments, or metadata is needed:

```java
public class ClientRegistrar implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
            new RootBeanDefinition(RemoteClient.class);

        registry.registerBeanDefinition("remoteClient", definition);
    }
}
```

Importing the registrar:

```java
@Configuration
@Import(ClientRegistrar.class)
public class RemoteClientConfig {
}
```

Registrars are typically used in libraries or frameworks that register beans based on custom annotations. For regular application configuration, `@Bean`, importing static classes, or component scanning is easier to read and maintain.

## 8. Loading XML with `@ImportResource`

`@ImportResource` lets a Java configuration class load additional bean definitions from XML:

```java
@Configuration
@ImportResource("classpath:/spring/legacy-services.xml")
public class ApplicationConfig {

    @Bean
    public OrderFacade orderFacade(OrderService orderService) {
        return new OrderFacade(orderService);
    }
}
```

The XML file can declare beans:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyTaxCalculator"
          class="com.example.legacy.LegacyTaxCalculator"/>

</beans>
```

The `legacyTaxCalculator` bean is registered into the same `ApplicationContext` as the Java configuration beans. Beans can inject one another if their types and qualifiers match.

`@ImportResource` accepts one or more resource locations. You can use classpath resources or locations supported by the resource loader:

```java
@ImportResource({
    "classpath:/spring/legacy-datasource.xml",
    "classpath:/spring/legacy-services.xml"
})
```

The `classpath:` path keeps configuration independent of the current working directory. Confirm that files are packaged on the application classpath and that resource names match exact casing on case-sensitive filesystems.

## 9. Combining `@ComponentScan`, `@Import`, and `@ImportResource`

A root configuration can use all three mechanisms simultaneously:

```java
@Configuration
@ComponentScan(basePackages = "com.example.orders.components")
@Import({PersistenceConfig.class, SecurityConfig.class})
@ImportResource("classpath:/spring/legacy-integration.xml")
public class ApplicationConfig {
}
```

In this example:

- `@ComponentScan` finds components in the orders module.
- `@Import` composes Java configurations split by responsibility.
- `@ImportResource` loads legacy bean definitions from XML.
- `@Bean` methods in `ApplicationConfig` can add context-specific beans.

These mechanisms are not mutually exclusive. They all contribute bean definitions to the context. However, keep clear boundaries: which packages are scanned, which modules are imported, which XML files hold legacy beans, and which beans are configured with `@Bean`.

A package layout might look like:

```text
com.example.orders
├── ApplicationConfig.java
├── application
│   ├── PlaceOrderService.java
│   └── PricingService.java
├── adapter
│   ├── persistence
│   │   ├── PersistenceConfig.java
│   │   └── JpaOrderRepositoryAdapter.java
│   └── payment
│       └── HttpPaymentAdapter.java
└── security
    └── SecurityConfig.java

resources
└── spring
    └── legacy-integration.xml
```

In a modular application, `ApplicationConfig` acts as the composition root: the place that assembles the components needed to build the application's context.

## 10. Importing Java Configuration from XML

The reverse direction is also possible: XML can register a Java configuration class. Example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean class="com.example.orders.PersistenceConfig"/>

    <bean id="legacyTaxCalculator"
          class="com.example.legacy.LegacyTaxCalculator"/>
</beans>
```

`<context:annotation-config/>` registers the required annotation processing infrastructure, including the processor for Java configuration. The `PersistenceConfig` class is registered as a bean definition and processed to discover its `@Bean` methods and related configuration.

If XML already uses `<context:component-scan>`, the necessary annotation processing infrastructure is enabled automatically. You do not need to declare `annotation-config` again just for component scanning.

XML can also import other XML files using the `<import>` element:

```xml
<beans ...>
    <import resource="classpath:/spring/legacy-datasource.xml"/>
    <import resource="classpath:/spring/legacy-services.xml"/>
</beans>
```

This is the mechanism for composing XML with XML. If you want XML to bring Java configuration into the context, you can declare the configuration class as a bean as shown above, or use a Java-bootstrapped context to register both sources.

## 11. Using `XmlBeanDefinitionReader` to Load XML and Java Classes in the Same Context

When you want to control bootstrapping in Java code, you can use `XmlBeanDefinitionReader` alongside `AnnotationConfigApplicationContext`:

```java
var context = new AnnotationConfigApplicationContext();

var xmlReader = new XmlBeanDefinitionReader(context);
xmlReader.loadBeanDefinitions("classpath:/spring/legacy-context.xml");

context.register(ApplicationConfig.class);
context.refresh();

try {
    OrderService service = context.getBean(OrderService.class);
} finally {
    context.close();
}
```

This example loads XML bean definitions into the context, registers a Java configuration class, and calls refresh once to complete initialization. `AnnotationConfigApplicationContext` supports both annotation configuration and bean definitions loaded via a reader.

This approach is useful in plain Spring applications or tooling that needs to select configuration sources at runtime. In standard Spring Boot applications, placing `@ImportResource` on a configuration class is usually simpler.

## 12. Combining XML and Java Config in Spring Boot

Spring Boot favors Java configuration and auto-configuration, yet can still load XML when integrating legacy systems. Example:

```java
@SpringBootApplication
@ImportResource("classpath:/spring/legacy-context.xml")
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Spring Boot initializes the context from the application configuration, and then XML resources are processed alongside bean definitions from component scanning, auto-configuration, and `@Bean` methods.

If XML configuration is needed for only one module, you can place `@ImportResource` on a separate configuration class and import that class from the application:

```java
@Configuration
@ImportResource("classpath:/spring/legacy-billing.xml")
public class LegacyBillingConfig {
}
```

```java
@SpringBootApplication
@Import(LegacyBillingConfig.class)
public class OrdersApplication {
}
```

This organization gives the legacy module a clear boundary. When removing XML, you can replace `LegacyBillingConfig` with new Java configuration with minimal impact on the root configuration.

## 13. Beans Declared from Multiple Sources Can Inject Each Other

A bean declared in XML can be injected into Java configuration or component classes. Conversely, a bean created with `@Bean` can be referenced in XML using `ref`.

Example XML declaring a legacy adapter:

```xml
<bean id="legacyTaxCalculator"
      class="com.example.legacy.LegacyTaxCalculator"/>
```

A Java component injects that bean:

```java
@Service
public class InvoiceService {

    private final LegacyTaxCalculator taxCalculator;

    public InvoiceService(LegacyTaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }
}
```

Or XML references a bean created in Java:

```java
@Configuration
public class ClientConfig {

    @Bean
    public RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
```

```xml
<bean id="legacyFacade"
      class="com.example.legacy.LegacyFacade">
    <constructor-arg ref="remoteClient"/>
</bean>
```

The requirement is that both bean definitions belong to the same context or have a parent-child relationship allowing lookup in the right direction. If they reside in two independent contexts, the beans will not automatically see each other.

## 14. Handling Bean Names and Conflicts When Composing Configurations

When the same component is registered from multiple sources, problems can arise with bean names or type-based injection.

Example of two sources declaring the same name:

```java
@Configuration
class PaymentConfig {

    @Bean
    PaymentPort paymentPort() {
        return new SandboxPaymentAdapter();
    }
}
```

```xml
<bean id="paymentPort"
      class="com.example.payment.LivePaymentAdapter"/>
```

Two bean definitions with the same name `paymentPort` can lead to conflicts or overriding behavior depending on container configuration and environment. Spring Boot usually disables bean definition overriding by default to catch duplicate configurations early; plain Spring configuration and other versions/setups may have different policies. Do not rely on one bean accidentally overriding another.

If two implementations coexist under different names, type-based injection can become ambiguous:

```java
public OrderService(PaymentPort paymentPort) {
    this.paymentPort = paymentPort;
}
```

When multiple `PaymentPort` beans exist, you can use `@Qualifier` or `@Primary`:

```java
@Bean
@Primary
PaymentPort defaultPaymentPort() {
    return new SandboxPaymentAdapter();
}

@Bean
@Qualifier("livePayment")
PaymentPort livePaymentPort() {
    return new LivePaymentAdapter();
}
```

And inject by qualifier when needed:

```java
public OrderService(@Qualifier("livePayment") PaymentPort paymentPort) {
    this.paymentPort = paymentPort;
}
```

`@Primary` and `@Qualifier` resolve bean selection during type-based injection. They do not resolve two bean definitions registering the same bean name. Manage bean names explicitly and avoid registering the same class redundantly via scanning, importing, and XML unless intentional.

## 15. Profiles and Conditions When Combining Multiple Sources

A configuration may only be used in one environment. `@Profile` can be placed on configuration classes or bean methods:

```java
@Configuration
@Profile("production")
public class ProductionPaymentConfig {

    @Bean
    PaymentPort paymentPort() {
        return new LivePaymentAdapter();
    }
}
```

Meanwhile, development configuration can provide a sandbox adapter:

```java
@Configuration
@Profile("development")
public class DevelopmentPaymentConfig {

    @Bean
    PaymentPort paymentPort() {
        return new SandboxPaymentAdapter();
    }
}
```

Imported classes remain subject to profile/condition processing. If the profile is not active, the conditional bean or configuration will not be registered according to that annotation's rules.

XML can also use profiles:

```xml
<beans profile="development">
    <bean id="paymentPort"
          class="com.example.payment.SandboxPaymentAdapter"/>
</beans>
```

Ensure profiles are activated consistently across Java and XML. A Java configuration might import XML containing beans restricted to `production`; if a test runs with the `test` profile, those beans will be absent. In that case, provide a replacement bean for the test profile or adjust the configuration as intended.

## 16. Import Order and Dependencies Between Configurations

`@Import` expresses configuration composition, but array order in an import should not be used as a mechanism to control bean initialization order. Spring manages dependencies and lifecycles based on bean definitions, dependency injection, and dedicated ordering mechanisms.

If `OrderService` needs `PaymentPort`, declare the dependency via constructor. Do not rely on `PaymentConfig` being written before `OrderConfig` or appearing earlier in the import list.

When one bean must initialize after another, prefer expressing the actual dependency. `@DependsOn` can express initialization order by bean name in special cases, but should not replace normal dependency injection.

For both XML and Java config, the same principle applies: beans are instantiated as the container resolves dependencies and lifecycles, not simply in the order files are read. Avoid side effects while parsing configuration; reading metadata and registering definitions should remain separate from performing connections or writing real data.

## 17. Combining Configuration Sources in Tests

The TestContext Framework lets you supply multiple configuration classes or XML resources for a test context. Example with JUnit Jupiter:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = {TestSupportConfig.class, OrderTestConfig.class},
    locations = "classpath:/spring/legacy-test-beans.xml"
)
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrderUsingConfiguredAdapters() {
        // ...
    }
}
```

`classes` supplies Java configuration or component classes; `locations` supplies XML resources. Spring Test creates the context from the declared sources. With Spring Boot, you can select the test configuration via `@SpringBootTest(classes = ...)` and place `@ImportResource` on the selected configuration class.

A Java test configuration can import a real module and replace an adapter:

```java
@TestConfiguration
@Import({OrderModuleConfig.class, PersistenceTestConfig.class})
class OrderTestConfig {

    @Bean
    @Primary
    PaymentPort paymentPort() {
        return new FakePaymentAdapter();
    }
}
```

When using `@TestConfiguration` with Spring Boot, the class can supplement beans for tests without being picked up as a main application configuration during regular component scanning. `@Primary` helps select the fake when multiple beans share a type, though you must still confirm no duplicate bean names exist.

### Testing Composed Configurations

A small context test can verify that important beans are actually registered:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ApplicationConfig.class)
class ApplicationConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersJavaAndXmlBeans() {
        assertNotNull(context.getBean(OrderService.class));
        assertNotNull(context.getBean("legacyTaxCalculator"));
        assertNotNull(context.getBean(PaymentPort.class));
    }
}
```

This test only verifies that the context can provide the required beans. If you need to verify which bean is injected when multiple implementations exist, assert the specific bean or the behavior of the component using it.

## 18. Parent Context and Child Context

In web applications or applications with multiple configuration regions, Spring may use a parent-child `ApplicationContext`. A child context can look up beans from its parent; a parent cannot look up beans that only exist in the child.

For example, a traditional web architecture might place services and repositories in the root context, while controllers and web-specific beans sit in the servlet context. When combining XML and Java config, identify which context each source is loaded into.

If `PaymentPort` is only declared in the child context while a service in the parent context needs it, the dependency cannot be resolved because the parent cannot see child beans. Place beans in the context with the appropriate scope or adjust the context architecture.

You do not need to create multiple contexts just to separate XML files from Java config. If beans need to inject one another, they should normally be loaded into the same context. Parent-child contexts are only useful when genuinely distinct lifecycle or visibility boundaries exist.

## 19. Organizing a Migration from XML to Java Configuration

In legacy systems, migrating configuration should happen incrementally and verifiably. A practical roadmap:

1. **Inventory XML beans:** record bean ids, classes, constructors/properties, aliases, scopes, init/destroy methods, and dependencies.
2. **Identify modules:** group beans by persistence, integration, business services, web, or security.
3. **Create corresponding Java configurations:** move one group of beans to `@Bean`, component classes, or dedicated configurations.
4. **Keep XML for unmigrated parts:** load via `@ImportResource` or an XML reader.
5. **Avoid duplicate declarations:** give each bean a single clear owner during the transition.
6. **Verify wiring:** initialize the context and confirm dependencies are injected properly.
7. **Test behavior:** run integration tests for flows using the migrated beans.
8. **Remove old XML once unreferenced:** update bootstrap configuration and documentation to avoid dead configuration sources.

Avoid migrating all XML in one big change if the system has many interdependent beans and lacks test coverage. Migrating module by module isolates failures, eases rollbacks, and cuts down investigation time when the context fails to start.

## 20. Common Mistakes When Combining Component Classes, XML, and `@Import`

- **Forgetting to load the XML resource:** `@ImportResource` points to the wrong path or the file is not on the classpath, causing XML beans to be missing.
- **Scanning packages too broadly:** components outside the application scope get registered and cause dependency conflicts.
- **Declaring the same bean twice:** a component is both scanned and imported or redeclared in XML with the same name.
- **Confusing `@Import` with `@ImportResource`:** `@Import` takes classes/selectors/registrars; XML resources require `@ImportResource` or an XML reader.
- **Confusing component annotations with component scanning:** having `@Component` on a class does not mean Spring finds it automatically; the class must be registered directly, imported, or within a scanned package.
- **Ambiguous injection:** multiple beans of the same type are registered without an appropriate qualifier or primary marker.
- **Using `@Primary` to fix duplicate bean names:** primary only affects selection by type, not duplicate definitions sharing a name.
- **Relying on file order:** a configuration read earlier does not guarantee its beans are always created first; express real dependencies.
- **Profile mismatch:** Java config and XML have different profile conditions, preventing required beans from being registered.
- **Placing beans in the wrong context:** parent and child contexts do not see beans in the expected direction.
- **Using `@DirtiesContext` instead of fixing configuration:** the context gets recreated, but wiring errors or duplicate beans remain.

## 21. Choosing the Right Mechanism

| Need | Mechanism to Consider |
| --- | --- |
| Register a few known classes | `AnnotationConfigApplicationContext.register(...)` |
| Discover services/repositories/controllers by package | `@ComponentScan` or `<context:component-scan>` |
| Compose Java configuration modules | `@Import` |
| Add a specific component class to a module | `@Import(ComponentClass.class)` or direct registration |
| Select configuration dynamically from metadata | `ImportSelector` |
| Register bean definitions at a low level | `ImportBeanDefinitionRegistrar` |
| Load XML from Java config | `@ImportResource` |
| Load Java configuration from XML | Register configuration class in XML with annotation processing enabled |
| Load both XML and classes programmatically | `XmlBeanDefinitionReader` with `AnnotationConfigApplicationContext` |
| Add configuration for tests | `@ContextConfiguration`, `@TestConfiguration`, `@ImportResource` |

A clean configuration typically has one composition root responsible for assembling modules, each module has its own configuration class, component scanning is bounded by package, and XML is retained only where integration still requires it. This organization makes it clear where beans come from, why they are registered, and which context owns them.

## 22. Diagnostic Workflow When a Bean Is Missing or Mis-Injected

When the context fails to start or injects the wrong bean, check in order:

1. **Registration source:** is the class registered, imported, scanned, or declared in XML?
2. **Resource path:** is the XML on the classpath and does `@ImportResource` point to the right path?
3. **Scan boundary:** does the scanned package include the component class and does it accidentally include unwanted modules?
4. **Annotation processing:** has the XML context enabled the processors needed for annotations/configuration?
5. **Bean name:** do component names, `@Bean` methods, XML ids, and aliases collide?
6. **Bean type:** are there multiple implementations of the same type; is `@Qualifier` or `@Primary` needed?
7. **Profile/condition:** do active profiles and properties allow the bean to be registered?
8. **Context hierarchy:** does the bean live in the parent or child context, and can the consumer see it?
9. **Lifecycle:** has the context been refreshed and was the bean instantiated successfully?
10. **Test configuration:** did a test accidentally replace or add configuration that alters the bean set compared to runtime?

You can use `ApplicationContext.getBeanDefinitionNames()` to inspect bean definition names, `getBeanNamesForType(...)` to check beans by type, or enable appropriate logging for Spring configuration packages to trace parsing and registration. These steps are useful for diagnostics, though tests should assert meaningful application beans and behavior rather than depending on the entire internal bean list.

## 23. Summary

Spring can combine component classes, Java configuration, and XML within the same `ApplicationContext`. Direct class registration provides explicit component selection; component scanning discovers stereotypes within packages; `@Import` composes Java configurations or component classes; `@ImportResource` brings XML bean definitions into the context. XML can also register Java configuration when annotation processing is enabled, and `XmlBeanDefinitionReader` allows bootstrapping both sources programmatically.

When combining multiple sources, establish clear package boundaries, single ownership per bean, bean names, qualifiers, profiles, and context hierarchy. In Spring testing, provide the exact classes and resources needed to create reproducible contexts. When configuration sources are modularized and backed by tests verifying wiring, maintaining legacy systems or gradually migrating from XML to Java configuration becomes much easier to control.
