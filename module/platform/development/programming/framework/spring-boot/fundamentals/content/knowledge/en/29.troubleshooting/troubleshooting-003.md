# NoSuchBeanDefinitionException: Missing Beans or Out-of-Scope Registration

> **Spring Boot Fundamentals · Troubleshooting**  
> `NoSuchBeanDefinitionException` occurs when Spring needs to look up a bean by name or type but finds no matching bean in the queried `BeanFactory`/`ApplicationContext`. In a Spring Boot application, the cause is rarely "Spring is broken"; instead, the bean was not registered, bean-creating configuration was not activated, the component lies outside the scan scope, a dependency is missing from the classpath, or code is looking up the bean with the wrong name/type. To fix it properly, determine **who is requesting the bean, which context is being queried, which mechanism was supposed to create the bean, and whether those registration conditions are actually met**.

## 1. Meaning of NoSuchBeanDefinitionException

Spring manages objects through a container. An object registered in the container is called a **bean**. When a component needs a dependency, Spring searches for a compatible bean to inject. If no matching bean exists, initialization or lookup fails.

Example:

```java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

If no bean implementing `PaymentGateway` is registered in the context, Spring cannot create `CheckoutService`. The error may appear as an outer `UnsatisfiedDependencyException` with `NoSuchBeanDefinitionException` in the cause chain.

Another case is manual lookup in code:

```java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
```

If the context has no corresponding bean, this operation throws `NoSuchBeanDefinitionException` directly.

### 1.1. Common Error Messages

Example:

```text
No qualifying bean of type
'com.example.payment.PaymentGateway' available
```

Or:

```text
No bean named 'paymentGateway' available
```

These two messages indicate two different lookup modes:

- **Lookup by type:** Spring needs a bean whose type is compatible with `PaymentGateway`.
- **Lookup by name:** Spring needs a bean with the exact name `paymentGateway`.

If lookup by type finds no bean, the bean may not exist yet or may not be compatible. If lookup by name fails, the bean may exist under a different name.

### 1.2. Where Does the Error Commonly Appear?

`NoSuchBeanDefinitionException` can occur when:

- Spring instantiates a bean and cannot satisfy a constructor dependency.
- A `@Bean` method requires another bean that does not exist in the context.
- Code calls `ApplicationContext.getBean(...)`.
- A component uses `@Autowired` or `@Resource`, but the dependency is not properly registered.
- Auto-configuration or test configuration expects a bean whose conditions are not satisfied.
- A child context looks up a bean outside its visible scope.

Do not read only the first line of the stack trace. You usually need to see **which bean is being created**, **which dependency is missing**, and **which context is performing the lookup**.

## 2. Distinguishing Similar Exceptions

Bean-related errors have similar names but different causes.

| Exception | Meaning |
| --- | --- |
| `NoSuchBeanDefinitionException` | No bean matches the lookup criteria |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist, so Spring cannot choose a single one |
| `UnsatisfiedDependencyException` | A dependency could not be satisfied while creating a bean; may wrap an underlying cause |
| `BeanCreationException` | Bean could not be created; cause could be a dependency, constructor, init method, binding, or another error |
| `BeanCurrentlyInCreationException` | Usually involves a dependency cycle or accessing a bean currently under creation |
| `NoSuchBeanDefinitionException: No bean named ...` | No bean found under the requested name |

### 2.1. Missing Bean vs. Too Many Beans Are Opposite Scenarios

Suppose:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
```

If no implementation is registered, Spring reports a missing bean.

If there are two implementations:

```java
@Component
class StripeGateway implements PaymentGateway {
    // ...
}

@Component
class SandboxGateway implements PaymentGateway {
    // ...
}
```

and a service injects `PaymentGateway` without a clear selection, the error is usually `NoUniqueBeanDefinitionException` rather than `NoSuchBeanDefinitionException`.

### 2.2. Read the Root Cause, Not Just the Outermost Exception

Example:

```text
UnsatisfiedDependencyException
  └── NoSuchBeanDefinitionException:
      No qualifying bean of type 'PaymentGateway'
```

The key detail is in the cause: `PaymentGateway` is missing.

However, another case is:

```text
BeanCreationException
  └── IllegalStateException:
      Could not resolve placeholder 'payment.endpoint'
```

This is not a missing bean error. Spring found the bean, but creating it failed because a configuration property was missing.

**Distinguish bean lookup failures from bean instantiation failures.**

## 3. Where Does Spring Learn About a Bean?

Spring offers multiple ways to register beans. Common mechanisms:

1. Component scanning locates classes with stereotype annotations.
2. Configuration classes declare `@Bean` methods.
3. `@Import` brings configurations or components into the context.
4. Spring Boot auto-configuration creates beans conditionally.
5. Spring Test adds or replaces beans for tests.
6. Code programmatically registers beans via registries/contexts in specialized cases.

### 3.1. Component Stereotypes

Common annotations:

| Annotation | Meaning |
| --- | --- |
| `@Component` | Marks a class as a Spring-managed component |
| `@Service` | Stereotype commonly used for services |
| `@Repository` | Stereotype for persistence components; can participate in exception translation |
| `@Controller` | Spring MVC controller |
| `@RestController` | Controller returning response bodies by default |
| `@Configuration` | Class defining beans/configuration |
| `@ControllerAdvice` | Advice component for controllers |
| `@ConfigurationProperties` | Marks a configuration model class; requires registration via scan or enable mechanism |

Example:

```java
@Repository
public class JdbcOrderRepository implements OrderRepository {
    // ...
}
```

Stereotype annotations let component scanning recognize a class, yet **having the annotation alone does not guarantee bean creation**. The class's package must fall within scan scope or be registered another way.

### 3.2. Bean Methods with `@Bean`

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxGateway();
    }
}
```

When `PaymentConfiguration` is imported/scanned into the context, the `@Bean` method registers a bean with the default name `paymentGateway`.

If the configuration class is not discovered or imported, its bean methods are not processed in that context.

### 3.3. Registration via `@Import`

```java
@Configuration(proxyBeanMethods = false)
@Import(PaymentConfiguration.class)
public class ApplicationIntegrationConfiguration {
}
```

`@Import` pulls configuration classes or suitable components into the context. This is useful when a module should provide explicit configuration instead of relying solely on package scanning.

### 3.4. Spring Boot Auto-Configuration

A starter can provide auto-configuration that registers beans:

```java
@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
@ConditionalOnMissingBean(PaymentGateway.class)
public class PaymentAutoConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentClient client) {
        return new RemotePaymentGateway(client);
    }
}
```

The bean is created only if its conditions hold. If `PaymentClient` is not on the classpath, or the user already supplied another bean, auto-configuration may skip creating the default bean.

Spring Boot 3 uses the auto-configuration registration file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

If an auto-configuration class is missing from this file or improperly imported, it may not be discovered at startup.

## 4. Most Common Cause: Component Lies Outside Scan Scope

This commonly happens when the package structure is not aligned around the application root.

Example:

```text
com.example.shop
├── ShopApplication.java
├── order
│   └── OrderService.java
└── payment
    └── PaymentGatewayImpl.java
```

Application root:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

By default, `@SpringBootApplication` performs component scanning from the annotated class's package and its subpackages. Since `com.example.shop.order` and `com.example.shop.payment` are subpackages, matching components are discovered.

### 4.1. Placing the Application Class Too Deep

Example:

```text
com.example.shop
└── bootstrap
    └── ShopApplication.java
com.example.shop.payment
    └── PaymentGatewayImpl.java
```

If `ShopApplication` is in `com.example.shop.bootstrap`, default component scanning starts at that package and its subpackages—it does not scan upward into `com.example.shop.payment`.

The `PaymentGatewayImpl` bean sits outside the scan scope.

### 4.2. Fix: Place the Root Application in the Parent Package

Usually the easiest approach to maintain:

```text
com.example.shop
├── ShopApplication.java
├── bootstrap/
├── order/
├── payment/
└── customer/
```

Placing the `@SpringBootApplication` class at the root application package scans all child modules cleanly by convention.

### 4.3. Fix: Specify `scanBasePackages`

If the package structure must remain as is:

```java
@SpringBootApplication(
        scanBasePackages = {
            "com.example.shop.bootstrap",
            "com.example.shop.order",
            "com.example.shop.payment"
        }
)
public class ShopApplication {
}
```

This resolves component scanning, though be careful as broadening scan scope may pick up unintended beans.

### 4.4. `scanBasePackages` Does Not Replace All Other Scan Mechanisms

An important detail: `@SpringBootApplication`'s `scanBasePackages` primarily configures component scanning. It does not automatically control every other scanning mechanism, such as JPA entity scanning or Spring Data repository scanning in all setups.

If JPA repositories or entities are missing, you may need `@EnableJpaRepositories`, `@EntityScan`, or appropriate package configuration depending on architecture. Never assume one component scan change fixes every registry type.

## 5. Class Has an Annotation Yet the Bean Still Does Not Exist

Check each condition:

### 5.1. Is the Annotation Present and Appropriate?

Example class:

```java
public class PaymentGatewayImpl implements PaymentGateway {
}
```

The class has no stereotype, no `@Bean` declaration, no `@Import`, and no other registration mechanism. Thus Spring does not know to create this bean.

Possible fix:

```java
@Component
public class PaymentGatewayImpl implements PaymentGateway {
}
```

or declare it with `@Bean` in a configuration class.

### 5.2. Is It a Class Spring Can Manage?

Certain declarations may not work with component scanning or proxying as expected:

- The class is in an unscanned package.
- The class has no stereotype and is not imported.
- The class is a non-static inner class or has a structure unsuitable for bean instantiation.
- The class is abstract with no concrete implementation to instantiate.
- Its constructor requires another dependency that is also missing.
- The class is excluded by a component scan filter.

Spring does not turn every class on the classpath into a bean. The classpath holds bytecode; the container manages only beans registered via its mechanisms.

### 5.3. Downstream Constructor Dependencies Are Missing

Example:

```java
@Component
public class PaymentGatewayImpl implements PaymentGateway {

    public PaymentGatewayImpl(PaymentClient client) {
        // ...
    }
}
```

Even when `PaymentGatewayImpl` is scanned, Spring still cannot create it if `PaymentClient` has no bean.

The stack trace may report that `paymentGatewayImpl` could not be created because `PaymentClient` is missing. Do not just annotate the first implementation; follow the dependency chain to the first missing bean.

## 6. Bean Excluded by Profile

`@Profile` restricts beans by active profiles.

Example:

```java
@Configuration
@Profile("prod")
public class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

If the app runs with the `test` profile or without `prod` active, this configuration is skipped, so the `PaymentGateway` bean does not exist.

### 6.1. Checking Active Profiles

In code:

```java
@Component
public class ProfileReporter implements ApplicationRunner {

    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                Arrays.toString(environment.getActiveProfiles()));
    }
}
```

In tests:

```java
@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {
}
```

If only a `@Profile("prod")` configuration exists, the `test` profile will not create that bean.

### 6.2. Default Profile vs. Active Profile

When no active profile is declared, Spring may fall back to the default profile. Do not assume `default` and `prod` are identical.

Check these sources:

- `spring.profiles.active`.
- `spring.profiles.default`.
- `@ActiveProfiles` in tests.
- Environment variable `SPRING_PROFILES_ACTIVE`.
- Command-line arguments.
- Profile groups or include configurations if present.

### 6.3. One Bean per Environment

You can define separate implementations:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Profile("test")
    PaymentGateway testPaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway productionPaymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

When the profile is `test` or `prod`, the corresponding bean is registered. If neither profile is active, no bean exists.

You can provide a fallback for the default profile or use other conditions if the application requires the bean in every environment.

## 7. Bean Excluded by Conditional Annotations

Spring Boot auto-configuration and application configuration often use conditions so beans are created only when criteria hold.

### 7.1. `@ConditionalOnProperty`

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

If `app.payment.enabled` is missing or has a different value, the configuration is not activated.

Check config files:

```yaml
app:
  payment:
    enabled: true
```

Also check whether higher-precedence sources override the value to `false`.

### 7.2. `matchIfMissing`

```java
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
```

With `matchIfMissing=true`, the condition matches when the property is absent, per annotation semantics. Do not use this attribute if missing configuration should fail or if the feature should default to disabled.

### 7.3. `@ConditionalOnClass`

```java
@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
public class PaymentAutoConfiguration {
    // ...
}
```

If the required class is absent from the runtime classpath, auto-configuration is not enabled.

Inspect the dependency tree or the built artifact. A dependency present only at compile/test scope yet missing at runtime produces the same result.

### 7.4. `@ConditionalOnMissingBean`

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultPaymentGateway() {
    return new SandboxPaymentGateway();
}
```

The default bean is created only if no matching bean exists yet. If the application already registered another implementation, the absence of the default bean is **expected behavior**.

However, if a component looks up a bean specifically named `paymentGateway` while the custom bean has a different name, name lookup can fail even though another `PaymentGateway` exists.

### 7.5. Other Conditions

Other annotations:

- `@ConditionalOnBean`.
- `@ConditionalOnMissingBean`.
- `@ConditionalOnClass`.
- `@ConditionalOnMissingClass`.
- `@ConditionalOnResource`.
- `@ConditionalOnExpression`.
- `@ConditionalOnWebApplication`.
- `@ConditionalOnNotWebApplication`.
- `@ConditionalOnSingleCandidate`.

When a bean does not appear, do not search only for `@Component`. Inspect all configuration classes, imports, and conditions governing bean registration.

## 8. Configuration Class Not Imported or Discovered

Example:

```java
@Configuration(proxyBeanMethods = false)
public class MessagingConfiguration {

    @Bean
    MessagePublisher messagePublisher() {
        return new InMemoryMessagePublisher();
    }
}
```

If `MessagingConfiguration` sits outside component scan scope and is not imported, `messagePublisher` will not exist.

### 8.1. Using `@Import`

```java
@SpringBootApplication
@Import(MessagingConfiguration.class)
public class ShopApplication {
}
```

Or import it from another registered configuration class.

### 8.2. Checking Module Configuration

In a multi-module project:

```text
shop-app
├── ShopApplication
└── dependencies:
    ├── shop-core
    └── shop-messaging
```

Merely adding `shop-messaging` as a build dependency does not guarantee its configurations are discovered automatically. If a module is structured as a plain library, it may require:

- Proper component scanning.
- `@Import` from the application.
- Auto-configuration registered via Spring Boot's mechanism.
- A starter pulling auto-configuration onto the classpath.

Do not confuse **having a JAR in the dependency graph** with **importing configurations inside that JAR**.

### 8.3. Library Auto-Configuration Needs a Registration Entry

In Spring Boot 3, auto-configuration classes are typically registered in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example content:

```text
com.acme.messaging.autoconfigure.MessagingAutoConfiguration
```

If the file is missing, has a typo in the class name, is not packaged, or the dependency is missing from the runtime classpath, Boot cannot load the auto-configuration as intended.

## 9. `@ConfigurationProperties` Not Registered as a Bean

This is a distinct cause that is frequently overlooked.

Example:

```java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String endpoint;
    // getters/setters
}
```

`@ConfigurationProperties` describes how external properties bind to a class. It is **not a stereotype equivalent to `@Component`** in standard usage.

The class must be registered via an appropriate mechanism.

### 9.1. `@ConfigurationPropertiesScan`

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
}
```

Boot scans `@ConfigurationProperties` classes within the appropriate scan scope.

### 9.2. `@EnableConfigurationProperties`

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
```

This explicitly registers one or more properties classes.

### 9.3. Missing Registration Causes Missing Bean Errors

If a service injects `PaymentProperties` while the class only carries `@ConfigurationProperties` without being scanned/enabled, Spring reports that no bean was found.

Do not resolve this by arbitrarily slapping `@Component` onto every properties class. Use a registration mechanism consistent with your project's configuration architecture.

## 10. Wrong Bean Name or Wrong Lookup Type

A bean may exist while code looks it up under a different identifier.

### 10.1. Default Bean Names

Example:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {
}
```

The default bean name under component naming rules is usually the class name with a lowercase first letter:

```text
remotePaymentGateway
```

Do not assume this bean is named `paymentGateway` simply because the class implements `PaymentGateway`.

### 10.2. Explicit Naming

```java
@Component("paymentGateway")
public class RemotePaymentGateway implements PaymentGateway {
}
```

Or:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean("paymentGateway")
    PaymentGateway remotePaymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

If code must look up by name, the name must match the actual bean definition.

### 10.3. Prefer Injection by Type

Usually:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

is easier to refactor than:

```java
PaymentGateway gateway =
        context.getBean("paymentGateway", PaymentGateway.class);
```

Use lookup by name only when the bean name itself carries meaning, such as a registry selecting implementations by key. When only an interface dependency is needed, constructor injection by type is usually better.

### 10.4. Generic Types Can Affect Matching

Some beans have generic types or complex factory types. Spring can use generic metadata to distinguish candidates.

Example:

```java
public interface Handler<T> {
    void handle(T value);
}

@Component
class OrderHandler implements Handler<Order> {
    public void handle(Order value) {
    }
}

@Component
class InvoiceHandler implements Handler<Invoice> {
    public void handle(Invoice value) {
    }
```

When requesting `Handler<Order>`, generic metadata helps narrow the candidate. However, if code erases generic types or looks up raw `Handler.class`, results may be broader than intended, causing ambiguity or failing to match a specific typed bean.

## 11. The Bean Exists in a Different Context

An application may have multiple `ApplicationContext` instances, such as parent/child contexts, servlet web contexts, test context hierarchies, or manually constructed contexts.

A bean in one context is not necessarily visible from another context.

### 11.1. Parent and Child Contexts

In a hierarchy:

```text
Parent ApplicationContext
    ├── shared infrastructure beans
    └── Child WebApplicationContext
            ├── controllers
            └── web-specific beans
```

A child context can usually look up beans from its parent. The parent does not automatically see beans registered only in the child.

If code queries the parent for a controller that exists only in the web child, the lookup fails.

### 11.2. Servlet Context and Root Context

Some traditional web setups use a root WebApplicationContext and a child servlet context. When migrating or integrating legacy frameworks, verify which context owns the bean and which context handles the request.

Do not assume every bean in the entire web application lives in one flat registry.

### 11.3. Test Context Hierarchy

Spring Test supports context hierarchies in specialized tests. If a bean resides in a child context while the test injects from the parent, or test configuration builds an unexpected hierarchy, lookup failures can occur.

When using `@ContextHierarchy`, check carefully which configuration class belongs to each level.

### 11.4. Manually Created Contexts

If code manually creates:

```java
ApplicationContext context =
        new AnnotationConfigApplicationContext(
                SomeConfiguration.class);
```

that is a standalone container. It does not automatically share all beans from the running Spring Boot application context.

If you need beans from the application, inject the context/beans from the current container rather than creating a second context without the same configuration.

## 12. Test Slices Do Not Load All Application Beans

A common error in tests:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    OrderService orderService;
}
```

`@WebMvcTest` is a slice test focused on Spring MVC. It does not automatically construct the entire service/repository graph like a full application context. Thus, `OrderService` will not exist in the test context.

### 12.1. Mock Controller Dependencies

If the goal is to test the controller:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
```

`@MockitoBean` suits newer Spring Framework versions with bean override support. In older Spring Boot 3.x releases, projects typically used `@MockBean`; pick according to your version.

### 12.2. Use `@SpringBootTest` When Full Wiring Is Needed

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApplicationIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    MockMvc mockMvc;
}
```

This builds a broader context and creates real services along with their required dependencies per test configuration.

Do not convert every `@WebMvcTest` into `@SpringBootTest` just to silence missing bean errors. When slice tests are designed properly, mocking dependencies outside the slice is expected.

### 12.3. `@DataJpaTest` Is Also a Slice

`@DataJpaTest` focuses on JPA/repository infrastructure. Normal business services are not scanned into this context.

If a repository test needs a helper, import the required configuration or keep the test scoped appropriately. Do not expect every bean from `@SpringBootApplication` to appear in every test slice.

### 12.4. Test Bean Overrides Can Alter the Graph

`@MockBean`/`@MockitoBean` can add or replace beans in the test context. When using qualifiers or explicit names, ensure the override matches the bean your code requests.

## 13. Auto-Configuration Excluded or Not Imported

Spring Boot creates many beans based on dependencies and conditions.

For example, an application has:

```java
@Autowired
ObjectMapper objectMapper;
```

If Jackson is absent from the classpath or the corresponding auto-configuration is inactive, the bean may be missing in a customized context.

### 13.1. Check Runtime Dependencies

Check Maven:

```bash
./mvnw dependency:tree
```

Or Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

If a dependency is only in `testImplementation` or Maven `test` scope, the runtime application lacks the classes needed to trigger auto-configuration.

### 13.2. Inspect the Auto-Configuration Report

You can enable debug mode:

```properties
debug=true
```

Or run the application with the appropriate debug option so Spring Boot prints the Condition Evaluation Report.

The report shows which auto-configurations matched or did not match, typically with reasons such as:

- Required class missing from classpath.
- Property did not match.
- Another bean already exists.
- Incompatible web application type.
- Configuration was excluded.

This is one of the most useful tools when a default Spring Boot bean does not appear.

### 13.3. Check Exclusions

An application might exclude auto-configuration via:

```java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class ShopApplication {
}
```

Or property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

If the bean you need is created by an excluded auto-configuration, its absence is a direct result of configuration.

### 13.4. `@ConditionalOnMissingBean` May Prevent Creating the Default Bean

Do not immediately treat an auto-configuration "not creating a bean" as a bug. The application may already provide a custom replacement bean. Inspect existing beans by type and name before changing anything.

## 14. Bean Factories, Factory Methods, and Bean Products

Not every bean is created directly from a stereotyped class.

### 14.1. Factory Methods

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    PaymentClient paymentClient() {
        return new PaymentClient("https://payments.example.test");
    }
}
```

The bean is registered via the `@Bean` method. If the configuration is not loaded, the bean does not appear.

### 14.2. `FactoryBean`

Spring provides the `FactoryBean<T>` abstraction so a factory builds an object managed by the container as the bean product.

```java
public class ClientFactoryBean
        implements FactoryBean<PaymentClient> {

    @Override
    public PaymentClient getObject() {
        return new PaymentClient("https://payments.example.test");
    }

    @Override
    public Class<?> getObjectType() {
        return PaymentClient.class;
    }
}
```

If `ClientFactoryBean` is registered as `paymentClient`, looking up `paymentClient` returns the factory product; looking up `&paymentClient` returns the factory itself.

Looking up the wrong name or confusing the factory with its product can cause unexpected lookup/type errors.

### 14.3. Beans Can Be Lazily Initialized

A `@Lazy` bean or lazy singleton may not be instantiated until requested. However, lazy initialization does not mean the bean definition is missing.

Distinguish:

- **Missing bean definition:** the container has no definition for the bean.
- **Bean instance not yet created:** the definition exists, but instantiation is deferred.
- **Bean creation failed:** the definition exists, yet instantiating it failed.

`NoSuchBeanDefinitionException` generally points to a lookup finding no definition/candidate, whereas instantiation failures raise other exceptions.

## 15. Optional Dependencies and Handling Non-Mandatory Beans

Not every dependency must exist in every environment.

### 15.1. `Optional<T>`

```java
@Service
public class ReportService {

    private final Optional<ExportClient> exportClient;

    public ReportService(Optional<ExportClient> exportClient) {
        this.exportClient = exportClient;
    }

    public void exportIfAvailable() {
        exportClient.ifPresent(ExportClient::export);
    }
}
```

If no `ExportClient` exists, Spring injects `Optional.empty()`.

### 15.2. `ObjectProvider<T>`

```java
@Service
public class ReportService {

    private final ObjectProvider<ExportClient> exportClientProvider;

    public ReportService(
            ObjectProvider<ExportClient> exportClientProvider) {
        this.exportClientProvider = exportClientProvider;
    }

    public void exportIfAvailable() {
        ExportClient client = exportClientProvider.getIfAvailable();

        if (client != null) {
            client.export();
        }
    }
}
```

`ObjectProvider` supports on-demand lookup, suited for optional dependencies or lazy retrieval.

Its methods have distinct semantics:

- `getObject()` requires the bean to exist; throws if absent.
- `getIfAvailable()` returns null when absent, yet still throws if multiple indistinguishable candidates exist.
- `getIfUnique()` returns the bean when one clear candidate exists; its behavior when non-unique differs from `getIfAvailable`.

Do not use a provider merely to hide a dependency that should be mandatory. If a service cannot operate without the dependency, direct constructor injection fails fast and makes requirements explicit.

### 15.3. `@Autowired(required = false)`

```java
@Autowired(required = false)
private ExportClient exportClient;
```

Optional field injection works in certain scenarios, but field injection hides dependencies and complicates testing. Constructor injection with `Optional<T>` or `ObjectProvider<T>` usually expresses intent more clearly.

### 15.4. Optional Does Not Fix Misconfiguration

If `PaymentGateway` is required for payments, making it optional only lets the application start in a broken state unable to fulfill business logic. Classify dependencies:

- Mandatory: inject directly and fail fast.
- Optional: express optionality and define behavior when absent.
- Environment-specific: provide beans via profiles/conditions and verify every environment has an implementation.

## 16. Qualifier, Primary, and Bean Name: When a Bean Exists Yet Is Not Selected

While multiple candidates usually cause `NoUniqueBeanDefinitionException`, misconfigured qualifiers or names can prevent Spring from finding any bean matching the stated criteria.

### 16.1. `@Qualifier`

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("remotePaymentGateway")
            PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

A bean must carry a matching qualifier/name. If the implementation is registered under a different name or the qualifier does not match, Spring cannot find a qualifying candidate.

### 16.2. `@Primary`

```java
@Component
@Primary
class RemotePaymentGateway implements PaymentGateway {
}
```

`@Primary` marks the preferred candidate when multiple beans of the same type exist. It does not create a new bean or fix an unregistered one.

### 16.3. Custom Qualifier Annotations

```java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface RemotePayment {
}
```

Usage:

```java
@Component
@RemotePayment
class RemotePaymentGateway implements PaymentGateway {
}
```

```java
public CheckoutService(@RemotePayment PaymentGateway gateway) {
    this.gateway = gateway;
}
```

If a custom qualifier is placed in the wrong location or no bean bears that qualifier, Spring cannot resolve the dependency.

## 17. Repository and Entity Registration Scope Differs from Component Scan

Some developers fix component scanning yet still miss repositories or entities because they are managed by dedicated mechanisms.

### 17.1. Spring Data Repositories

Example:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
```

Spring Data creates proxy beans for repository interfaces when repository scanning is configured appropriately.

In a typical Spring Boot app, auto-configuration and the root application package detect repositories by convention. When repositories reside in another module/package, you may need:

```java
@EnableJpaRepositories(
        basePackages = "com.example.shared.persistence"
)
```

If a repository is not created, check:

- Is the Spring Data dependency on the classpath?
- Are JPA repositories enabled?
- Does package scanning cover the interface?
- Does the interface extend a valid repository interface?
- Is there an excluding profile/condition or configuration?

### 17.2. JPA Entities

Entities are not ordinary Spring beans. `@Entity` marks a type managed by the persistence provider—it does not mean the class can be injected via `@Autowired`.

For entity metadata, JPA scanning must discover the entity. Attempting to inject an entity class directly like a Spring service usually indicates confusion about lifecycles.

Use `@EntityScan` when customizing entity scan packages in appropriate configurations.

### 17.3. Repository Bean vs. Entity Type Are Two Concepts

A repository is typically a Spring bean generated by Spring Data. An entity is managed by the JPA persistence context/EntityManager. Never look up an entity via `ApplicationContext.getBean(Order.class)` unless you genuinely defined a separate Spring bean of that type.

## 18. Component Scan Filters and Bean Exclusion Rules

Even when the package is right, component scanning can skip a class due to filters.

Example:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = DeprecatedComponent.class
    )
)
@Configuration
class CustomScanConfiguration {
}
```

A class annotated with `@Component` that also carries the excluded annotation will not be registered by that scan.

Other scenarios:

- `useDefaultFilters=false` disables default stereotype filters.
- Exclude filters by assignable type.
- Custom include filters fail to match.
- Multiple `@ComponentScan` annotations with differing scopes.
- Scan configuration replaced in a test context.

If a component fails to appear, search for `@ComponentScan` declarations and filters across all relevant configurations.

## 19. Diagnosing with ApplicationContext

When the application starts successfully yet a specific lookup still fails, you can inspect existing beans.

### 19.1. Listing Beans by Type

```java
@Component
public class BeanReporter implements ApplicationRunner {

    private final ApplicationContext context;

    public BeanReporter(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] names =
                context.getBeanNamesForType(PaymentGateway.class);

        System.out.println(
                "PaymentGateway beans: "
                        + Arrays.toString(names));
    }
}
```

If the array is empty, the queried context sees no beans of that type within its scope.

If one or more names appear, check:

- Does the bean name match any lookup by name?
- Is the bean of the exact expected type?
- Does it have matching qualifiers?
- Which context owns the bean?
- Is the bean a `FactoryBean` product?

### 19.2. Checking Bean Names

```java
for (String name : context.getBeanDefinitionNames()) {
    if (name.toLowerCase(Locale.ROOT).contains("payment")) {
        System.out.println(name);
    }
}
```

This helps when a bean might be registered under a different name.

Do not routinely dump the entire bean list to production logs; output can be huge and leak internal details.

### 19.3. Checking the Bean's Runtime Class

```java
Map<String, PaymentGateway> gateways =
        context.getBeansOfType(PaymentGateway.class);

gateways.forEach((name, bean) -> {
    System.out.println(
            name + " -> " + bean.getClass().getName());
});
```

If the bean is wrapped by a proxy, its runtime class may be a proxy class. To determine the target type, use appropriate Spring AOP utilities rather than assuming `bean.getClass()` is always the original implementation class.

### 19.4. Inspecting Bean Definitions

With `ConfigurableApplicationContext`, you can inspect the `BeanDefinition` registry for registration metadata. Example:

```java
ConfigurableApplicationContext configurable =
        (ConfigurableApplicationContext) context;

String[] names =
        configurable.getBeanFactory().getBeanDefinitionNames();

System.out.println(Arrays.toString(names));
```

This is a debugging aid; do not arbitrarily mutate the registry after context refresh just to force a bean to exist.

### 19.5. Using Actuator `beans`

If Spring Boot Actuator is present and the `beans` endpoint is appropriately exposed and secured, `/actuator/beans` reports beans and their dependencies.

Expose this endpoint only in controlled environments. It reveals internal application structure and must not be left open publicly without need.

## 20. Condition Evaluation Report: Why Didn't Auto-Configuration Create the Bean?

When a bean is expected from a Spring Boot starter, the condition report is one of the first places to check.

### 20.1. Enabling Debug

In a test or local config:

```properties
debug=true
```

Or on the command line:

```bash
java -jar shop.jar --debug
```

Boot prints a report of matched and unmatched auto-configuration conditions.

### 20.2. Reading Unmatched Reasons

For example:

```text
PaymentAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class
        'com.acme.payment.PaymentClient'
```

Or:

```text
PaymentAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty (app.payment.enabled=true)
        found different value
```

This reveals whether a dependency is missing or a property condition failed.

### 20.3. Distinguish Configuration-Level vs. Bean-Method Conditions

A configuration class may be loaded while an individual `@Bean` method is skipped by a condition. Conversely, the entire configuration class might not be imported.

Pinpoint exactly where the condition sits:

- On the auto-configuration class.
- On a nested configuration class.
- On individual `@Bean` methods.
- On a component class.
- On a conditionally imported configuration.

Do not see a class name in the report and assume all its `@Bean` methods were created.

## 21. Systematic Diagnostic Workflow

When encountering `NoSuchBeanDefinitionException`, proceed in order:

### Step 1 — Identify the Missing Bean

Read:

```text
No qualifying bean of type '...'
No bean named '...'
```

Record the type or name Spring is looking for.

### Step 2 — Locate What Requests the Dependency

Find the constructor parameter, `@Autowired`, `@Resource`, `@Bean` method parameter, or `getBean(...)` call triggering the lookup.

Identify the parent bean being created and which dependency is missing.

### Step 3 — Identify the Queried Context

Does the app use parent/child contexts? Does a test use a context hierarchy? Does code instantiate a second `ApplicationContext` manually?

A bean in another context is not necessarily visible from the current context.

### Step 4 — Check the Bean Registration Mechanism

Where should the bean come from:

- `@Component` scan?
- `@Bean` method?
- `@Import`?
- Spring Boot auto-configuration?
- Spring Data repository scan?
- `@ConfigurationPropertiesScan`?
- Test bean override?
- Programmatic registry?

If you cannot identify what should create the bean, you do not yet have a basis for fixing it.

### Step 5 — Check Packages and Classpath

If using component scan, verify the package lies in scan scope. If using auto-configuration, verify the dependency is on the runtime classpath and imports metadata is packaged.

### Step 6 — Check Profiles and Conditions

Check active profiles, property values, and the Condition Evaluation Report. Look for unmatched conditions or excluded configurations.

### Step 7 — Check Name, Type, and Qualifiers

Does the bean exist under another name? Does it implement the right interface? Does the qualifier match? Are generic types different? Is a `FactoryBean` involved?

### Step 8 — Check Test Context Type

If the error occurs in a test, check whether it uses a full context or a slice. The missing bean may intentionally sit outside the slice's scope.

### Step 9 — Trace the Dependency Chain

A bean may fail to appear because its own configuration depends on another missing bean. Trace back to the first root cause rather than only the final affected class.

### Step 10 — Fix at the Right Boundary and Verify

Register/import/scan/configure the bean as designed. Then run a context startup test or behavior test. Never scatter annotations blindly just to silence exceptions.

## 22. Complete Example: Fixing a Missing PaymentGateway

### 22.1. Initial Structure

```text
com.example.shop
├── ShopApplication.java
├── checkout/
│   └── CheckoutService.java
└── infrastructure/
    └── payment/
        └── RemotePaymentGateway.java
```

However, the application class was actually placed in:

```text
com.example.shop.bootstrap.ShopApplication
```

Service code:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Implementation:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {
    // ...
}
```

Because component scan starts only from `com.example.shop.bootstrap`, `com.example.shop.infrastructure.payment` lies outside the scan scope.

### 22.2. Fix via Root Package

Move `ShopApplication` up to `com.example.shop`:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Now subpackages `checkout` and `infrastructure.payment` are scanned.

### 22.3. Or Import Configuration Explicitly

If the root package cannot be moved, create:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

and import it:

```java
@SpringBootApplication
@Import(PaymentModuleConfiguration.class)
public class ShopApplication {
}
```

Ensure the configuration class is imported and its dependencies are available.

### 22.4. Write a Test Verifying the Bean Graph

```java
@SpringBootTest(classes = ShopApplication.class)
class PaymentWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void paymentGatewayIsRegistered() {
        assertThat(context.getBean(PaymentGateway.class))
                .isNotNull();
    }
}
```

This test confirms a matching bean exists in the full test context. If multiple implementations exist, test selection or use appropriate qualifiers/primary.

### 22.5. Test Behavior Instead of Only Existence

An integration test can invoke the service and verify it uses the expected gateway. If the gateway calls an external system, replace it with a fake/test implementation in test configuration to avoid external side effects.

The goal is verifying wiring against the test contract, not necessarily calling a production payment provider.

## 23. Special Cases to Watch Out For

### 23.1. Request/Session-Scoped Beans

A web-scoped bean like `request` or `session` may not be accessible in a non-web context where that scope is unregistered. This typically produces a different scope/context error and should not be conflated with simple singleton beans.

If a test uses `webEnvironment=NONE` while a bean requires request scope, use an appropriate web test environment or mock that boundary.

### 23.2. Lazy Beans

`@Lazy` defers instance creation, yet the bean definition still exists. If a type lookup finds no bean, inspect registration/conditions rather than blaming lazy initialization.

### 23.3. Beans Created with Generic Types

A bean factory returning an overly broad type or obscuring the product type prevents Spring from predicting the type before instantiation. Ensure `@Bean` methods declare sufficiently concrete return types, especially when auto-configuration relies on `@ConditionalOnBean` or generic injection.

Example:

```java
@Bean
PaymentGateway paymentGateway() {
    return new RemotePaymentGateway();
}
```

is clearer than declaring return type `Object` when the bean is actually a `PaymentGateway`.

### 23.4. Classloaders and Duplicate Classes

In DevTools restart or plugin/container classloader setups, the same class name can be loaded by different classloaders. A bean may exist yet not be assignable to the consumer's loaded type depending on how Spring matches candidates.

Typical symptoms include `ClassCastException` or no matching candidate by type. Check classloaders and class identity if package/type names match yet lookup behaves strangely.

### 23.5. Beans Overridden or Replaced in Tests

Tests may register mocks or fakes for the same type/name. If an override mismatches qualifiers or bean names, the dependency may still appear missing or resolve to the wrong bean.

Check bean override annotations matching your Spring Boot/Spring Framework version.

## 24. Bad Fixes to Avoid

| Approach | Why It Is Bad | Better Approach |
| --- | --- | --- |
| Putting `@Component` on every class | Creates unneeded beans, ignores configuration boundaries | Register beans intentionally |
| Broadening component scan to an overly wide root package | Picks up unexpected beans, increases startup coupling | Choose clear package/module boundaries |
| Turning a mandatory dependency into `Optional` so the app boots | Hides wiring errors and produces broken behavior | Fix bean registration or provide an implementation |
| Adding `@Primary` when no bean exists | `@Primary` does not create beans | Ensure at least one candidate exists |
| Creating `new AnnotationConfigApplicationContext` inside a service | Spawns a separate container lacking the same graph | Inject beans from the managed context |
| Replacing every slice test with `@SpringBootTest` | Slows tests and blurs boundaries | Use the right test type |
| Excluding auto-configuration to silence errors | Removes needed beans and triggers other failures | Read the condition report |
| Adding a JAR to compile classpath without runtime | Auto-configuration sees no class at runtime | Check runtime dependencies |
| Looking up beans by guessed names | Bean names may differ | Inject by type or name explicitly |
| Ignoring the root cause | Outermost exception may only be a wrapper | Read the cause chain |
| Catching exceptions and continuing with null | Converts wiring failure into hard-to-find runtime bugs | Fail fast or model optionality intentionally |

## 25. Practice Exercise: Finding and Fixing a Missing Bean

### Objective

Create a Spring Boot application where `CheckoutService` requires `PaymentGateway`. Intentionally trigger missing bean scenarios to practice diagnosis.

### Step 1 — Create the Interface and Service

```java
public interface PaymentGateway {
    String charge(int amount);
}
```

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout(int amount) {
        return gateway.charge(amount);
    }
}
```

### Step 2 — Intentionally Omit the Implementation

Start the application. Observe the exception chain and note which bean was being created and which dependency was missing.

### Step 3 — Add an Implementation Outside Scan Scope

Place `PaymentGatewayImpl` in a package outside the application's root package. Keep `@Component` and restart.

Observe why the annotation is present yet the bean still goes undiscovered.

### Step 4 — Fix Component Scanning

Move the application class to the root package or configure the appropriate scan scope. Restart and confirm the bean is created.

### Step 5 — Try Profiles

Move the implementation into a configuration with `@Profile("prod")`, then run with the `test` profile. Observe the bean disappearing.

Add an implementation for the `test` profile or select the active profile suited to your test goal.

### Step 6 — Try Property Conditions

Add `@ConditionalOnProperty` to the configuration. Run with the property missing, false, and true. Read the Condition Evaluation Report to understand the outcomes.

### Step 7 — Try Bean Naming

Register the bean as `remoteGateway` while intentionally looking up `paymentGateway`. Observe lookup by name failing even though the typed bean exists. Fix via type injection or matching names.

### Step 8 — Try Test Slices

Write a `@WebMvcTest` for a controller needing `CheckoutService`. Observe that the service does not automatically appear in the slice. Add a mock bean or switch to a full-context test depending on goal.

### Step 9 — Inspect ApplicationContext

Use `getBeanNamesForType(PaymentGateway.class)` and `getBeanDefinitionNames()` to inspect the registry. Compare outputs as profiles/conditions change.

### Step 10 — Write a Regression Test

Create a `@SpringBootTest` verifying the critical bean graph exists and a behavioral test for checkout. If the test uses a fake gateway, note clearly that real external payment integration is not tested.

### Self-Check Questions

1. What does `NoSuchBeanDefinitionException` mean?
2. How does it differ from `NoUniqueBeanDefinitionException`?
3. Why can `UnsatisfiedDependencyException` wrap `NoSuchBeanDefinitionException`?
4. Does `@Component` alone guarantee a class becomes a bean in any package?
5. Where does `@SpringBootApplication`'s default component scan begin?
6. Why can placing the application class in a subpackage hide beans in sibling packages?
7. Does `scanBasePackages` control all JPA repository/entity scanning?
8. Under what condition is a `@Bean` method processed in a configuration class?
9. What problem does `@Import` solve?
10. Which file registers auto-configurations in Spring Boot 3?
11. When can `@ConditionalOnProperty` prevent a bean from appearing?
12. Why might `@ConditionalOnMissingBean` prevent a default bean from being created?
13. Does `@Profile("prod")` create beans under the `test` profile?
14. Why does `@ConfigurationProperties` usually require scanning or enable registration?
15. If a bean exists yet lookup by name fails, what should you check?
16. Does `@Primary` create a new bean?
17. Why might `@WebMvcTest` lack a service bean?
18. Does `@DataJpaTest` automatically scan the entire service layer?
19. Can a parent context see beans registered only in a child context?
20. How does `ObjectProvider<T>` differ from direct constructor injection?
21. When is an optional dependency the right design?
22. Does a `FactoryBean` differ from the bean product it produces?
23. Is a JPA entity a Spring bean meant for direct injection?
24. What does the Condition Evaluation Report help diagnose?
25. If the application starts yet a lookup still fails, how do you determine which context is being queried?

## 26. Quick Reference Table

| Symptom | First Place to Check |
| --- | --- |
| `No qualifying bean of type ...` | Is any bean assignable to that type? |
| `No bean named ...` | Does the bean name match? |
| `UnsatisfiedDependencyException` | Read the cause chain and the first missing dependency |
| Class has `@Component` yet is missing | Package scan, filters, active context |
| Bean from `@Bean` is missing | Was the configuration class imported/scanned? |
| Profile-specific bean is missing | `Environment.getActiveProfiles()` |
| Auto-configuration created no bean | Condition Evaluation Report |
| Property condition did not match | Property sources and effective value |
| Classpath condition did not match | Runtime dependency graph |
| `@ConfigurationProperties` cannot be injected | `@ConfigurationPropertiesScan` / `@EnableConfigurationProperties` |
| Repository was not created | Spring Data dependency and repository scanning |
| Entity not recognized | JPA entity scan; entities are not regular Spring beans |
| Bean exists yet lookup by name fails | Bean name, FactoryBean prefix, and context |
| Multiple candidates exist | `@Primary`, `@Qualifier`, or implementation selection design |
| Fails only in `@WebMvcTest` | Slice scope and mocked/imported dependencies |
| Fails only in a child context | Parent/child context hierarchy |
| Optional integration | `Optional<T>` or `ObjectProvider<T>` |
| Bean missing after DevTools restart | Check classloader, class identity, and lifecycle |
| Startup fails during bean init | Distinguish missing definition from creation exception |
| Want to inspect the registry | `getBeanNamesForType`, `getBeanDefinitionNames` |
| Want to verify wiring | `@SpringBootTest` or a test matching the scope |

**Conclusion:** `NoSuchBeanDefinitionException` signals that Spring found no matching bean in the queried context. Determine whether the lookup is by **type or name**, trace what requested the dependency, then inspect registration mechanisms, component scan scope, configuration imports, classpath, profiles, conditional annotations, qualifiers, and context hierarchy. When a bean is truly optional, express optionality with the proper API; when mandatory, fix registration so the application fails fast if the dependency is missing. A diagnostic workflow grounded in the bean graph and Condition Evaluation Report resolves root causes far faster than trial-and-error annotations or dependencies.
