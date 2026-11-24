# @ActiveProfiles and Bean Selection by Test Environment

A Spring application often needs different configurations when running on a developer's machine, in a test environment, and in production deployment. A repository may be replaced with a fake in tests, a mail client may write to a mock mailbox, while production uses an adapter connected to real services. Spring Profiles provide a mechanism to select configurations and beans based on the active environment.

In Spring TestContext, the `@ActiveProfiles` annotation declares the profiles to activate when loading the `ApplicationContext` for a test. The `@Profile` annotation on a component, configuration class, or `@Bean` method determines which components are registered when the corresponding profile is active. Combining these two annotations, tests can instruct Spring to wire the right group of beans for the test environment.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of Spring Profiles and `Environment`.
- Activate profiles for tests using `@ActiveProfiles`.
- Select implementations using `@Profile` on components and bean factory methods.
- Use profile expressions to combine environment conditions.
- Understand profile inheritance when a test class extends a base test class.
- Use a custom `ActiveProfilesResolver` when profiles need to be determined dynamically.
- Distinguish profiles from properties and other conditional mechanisms.
- Structure test configurations so that tests are independent of the host machine environment.

## 1. What Problem Do Spring Profiles Solve?

Consider a notification-sending application. When running in production, it needs to send emails via SMTP. In tests, we do not want to send real emails; instead, we can use an implementation that only records notifications in memory.

If we select the implementation using conditional statements scattered across services, business code would have to know which environment the application is running in. Spring Profiles allow placing that choice at the configuration and dependency injection layer.

~~~mermaid
flowchart TD
    A["Test initializes Spring TestContext"] --> B["@ActiveProfiles(test)"]
    B --> C["Environment has active profile test"]
    C --> D["Spring evaluates @Profile on beans"]
    D --> E["FakeEmailSender is registered"]
    E --> F["Test injects EmailSender"]
    G["Production starts up"] --> H["Profile production"]
    H --> I["SmtpEmailSender is registered"]
    I --> J["Application injects EmailSender"]
~~~

A profile is a name managed by `Environment`. For example:

- `test`: configuration and adapters for testing.
- `development`: configuration used during development.
- `staging`: configuration for the pre-production environment.
- `production`: real deployment configuration.

Profile names are conventions chosen by the application and development team. Spring does not mandate using these exact names. What matters is that profiles are activated intentionally and conditional beans accurately reflect their purpose.

Profiles are commonly used to select:

- Interface implementations, such as a fake repository versus a database-backed repository.
- Beans configuring HTTP clients, mail senders, or message publishers.
- Configuration classes providing datasources or integration adapters.
- Property files and environment-specific configurations.

Profiles are not an authorization mechanism or a security boundary. You should not rely on profile names to protect secrets or prevent an application from accessing production. Credentials and endpoints need to be managed with separate secure configurations.

## 2. Activating Profiles for Tests with @ActiveProfiles

`@ActiveProfiles` is a Spring TestContext annotation. It declares the profiles to activate when the framework loads the `ApplicationContext` for a test class.

Example:

~~~java
@SpringJUnitConfig(ApplicationConfiguration.class)
@ActiveProfiles("test")
class NotificationServiceTest {

    @Autowired
    NotificationService notificationService;

    @Test
    void sendsNotificationUsingTestConfiguration() {
        // Verify behavior with beans from the test profile.
    }
}
~~~

In this example, Spring creates an `Environment` for the context and activates the `test` profile. Beans conditioned on `@Profile("test")` can be registered. Beans intended only for other profiles will not be selected.

If no active profile is declared, Spring uses the default profile. The initial default name is `default`, though an application can change it via the `spring.profiles.default` configuration. When a test activates `test`, the `default` profile is not automatically added; only the currently active profiles determine the matching `@Profile` conditions.

Multiple profiles can be declared:

~~~java
@ActiveProfiles({"test", "local"})
class LocalIntegrationTest {
}
~~~

The profiles in the array are activated simultaneously. If a bean requires one of those profiles, you can use a profile array on `@Profile` or an appropriate expression.

Example:

~~~java
@Component
@Profile({"test", "local"})
class LocalEmailSender implements EmailSender {
    // Implementation used in test or local.
}
~~~

When a test class has `@ActiveProfiles`, Spring TestContext uses the declared list of profiles to set the active profiles for the context. Therefore, test results should not depend on whether the runner has set `spring.profiles.active` in an environment variable.

If you want to determine profiles based on the actual runtime environment, use `ActiveProfilesResolver` or configure the test without `@ActiveProfiles` and let the environment supply the profile. For unit and integration tests that need reproducibility, declaring profiles explicitly is usually easier to understand.

## 3. Selecting Beans with @Profile

`@Profile` sets a condition for Spring to register a component. The annotation can be used on:

- Classes discovered via component scanning, such as `@Component`, `@Service`, or `@Repository`.
- Configuration classes annotated with `@Configuration`.
- `@Bean` methods inside a configuration class.

### Selecting an implementation on a component

Suppose the application has an interface:

~~~java
public interface EmailSender {
    void send(String recipient, String message);
}
~~~

Implementation for tests:

~~~java
@Component
@Profile("test")
public class InMemoryEmailSender implements EmailSender {

    private final List<String> sentMessages = new ArrayList<>();

    @Override
    public void send(String recipient, String message) {
        sentMessages.add(recipient + ": " + message);
    }

    public List<String> sentMessages() {
        return List.copyOf(sentMessages);
    }
}
~~~

Implementation for production:

~~~java
@Component
@Profile("production")
public class SmtpEmailSender implements EmailSender {

    @Override
    public void send(String recipient, String message) {
        // Send via SMTP client configured for production.
    }
}
~~~

The service depends only on the interface:

~~~java
@Service
public class NotificationService {

    private final EmailSender emailSender;

    public NotificationService(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    public void notifyCustomer(String email, String message) {
        emailSender.send(email, message);
    }
}
~~~

When a test activates the `test` profile, Spring registers `InMemoryEmailSender`. When the application runs with the `production` profile, Spring registers `SmtpEmailSender`. The service does not need to know which concrete implementation is selected.

### Selecting a bean via @Bean method

If you want to place implementations in a configuration class, you can write:

~~~java
@Configuration
public class EmailConfiguration {

    @Bean
    @Profile("test")
    EmailSender testEmailSender() {
        return new InMemoryEmailSender();
    }

    @Bean
    @Profile("production")
    EmailSender productionEmailSender() {
        return new SmtpEmailSender();
    }
}
~~~

Different bean method names make the configuration clear. When only one matching profile is active at a time, the context will have one corresponding `EmailSender` bean to inject.

If two implementations are registered in the same context and both share the same type, Spring may throw an ambiguity error when injecting by type. Design profiles so that the matching bean set is unique, or use `@Qualifier`/`@Primary` when having multiple beans coexist is intentional.

## 4. Writing Tests to Confirm the Selected Implementation

You can directly verify the bean type provided by Spring. For example, using a configuration class:

~~~java
@Configuration
class EmailConfiguration {

    @Bean
    @Profile("test")
    EmailSender testEmailSender() {
        return new InMemoryEmailSender();
    }

    @Bean
    @Profile("production")
    EmailSender productionEmailSender() {
        return new SmtpEmailSender();
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(EmailConfiguration.class)
@ActiveProfiles("test")
class EmailProfileSelectionTest {

    @Autowired
    EmailSender emailSender;

    @Test
    void selectsInMemorySenderForTestProfile() {
        assertInstanceOf(InMemoryEmailSender.class, emailSender);
    }
}
~~~

This test initializes a real context, but only with the small configuration under test. `@ActiveProfiles("test")` satisfies the profile condition; `@Profile("test")` allows the factory method to register the bean. The assertion confirms that the injected bean is the right implementation.

You can verify behavior instead of just checking the class:

~~~java
@Test
void recordsMessagesWithoutSendingExternalEmail() {
    assertInstanceOf(InMemoryEmailSender.class, emailSender);

    emailSender.send("ada@example.com", "Order accepted");
    InMemoryEmailSender inMemory =
        (InMemoryEmailSender) emailSender;

    assertEquals(
        List.of("ada@example.com: Order accepted"),
        inMemory.sentMessages()
    );
}
~~~

## 5. @Profile Supports Conditional Expressions

`@Profile` can accept one or more profile names. When an array of profile names is passed, the bean is registered if at least one matching profile is active.

Example:

~~~java
@Configuration
@Profile({"test", "development"})
class NonProductionConfiguration {
}
~~~

This configuration is activated when the `test` or `development` profile is active.

Besides lists, Spring supports profile expressions with operators:

| Operator | Meaning | Example |
|---|---|---|
| `&` | AND | `test & cloud` |
| `|` | OR | `test | local` |
| `!` | NOT | `!production` |

Example:

~~~java
@Configuration
@Profile("test & !production")
class IsolatedTestConfiguration {
}
~~~

The configuration matches only when `test` is active and `production` is not active.

Expressions can be used to select beans for multiple environment combinations:

~~~java
@Bean
@Profile("development | test")
EmailSender localEmailSender() {
    return new InMemoryEmailSender();
}
~~~

~~~java
@Bean
@Profile("production & cloud")
EmailSender cloudEmailSender() {
    return new CloudEmailSender();
}
~~~

Complex expressions should be used sparingly. If a condition becomes hard to read, split the configuration into clear groups or use an appropriate custom condition.

## 6. Profile Inheritance in Test Classes

A test class can extend a base class containing shared test configuration. By default, `@ActiveProfiles` can be inherited from a superclass.

Example:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
@ActiveProfiles("test")
abstract class BaseSpringIntegrationTest {
}
~~~

~~~java
class OrderServiceIntegrationTest extends BaseSpringIntegrationTest {

    @Test
    void createsOrder() {
        // Context uses the inherited test profile.
    }
}
~~~

If a subclass adds a profile:

~~~java
@ActiveProfiles("database")
class DatabaseBackedOrderTest extends BaseSpringIntegrationTest {
}
~~~

By default `inheritProfiles` is true, so profiles from the superclass and subclass are combined. In this example, the context is requested to have both `test` and `database`.

If a subclass needs to replace the inherited profile list, set `inheritProfiles = false`:

~~~java
@ActiveProfiles(
    profiles = "postgres",
    inheritProfiles = false
)
class PostgreSqlIntegrationTest extends BaseSpringIntegrationTest {
}
~~~

At this point, profiles from the base class are not inherited for this test class. Choose between inheriting and replacing intentionally; if the base class profile contains essential conditions such as `test`, replacing it may cause test beans to no longer be registered.

When a test suite has multiple inheritance levels, clearly document which profiles come from the base class and which are added by subclasses. This helps prevent a test from unexpectedly running with a different set of beans than intended.

## 7. Using ActiveProfilesResolver When Profiles Must Be Determined Dynamically

Normally, tests should declare fixed profiles using `@ActiveProfiles("test")`. In some projects, profiles need to be selected based on a custom rule, such as the operating system, a system property, or the test type.

Spring TestContext allows implementing `ActiveProfilesResolver`:

~~~java
public class TestProfileResolver implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String selected = System.getProperty(
            "test.profile",
            "test"
        );

        return new String[] { selected };
    }
}
~~~

Attach the resolver to the test:

~~~java
@SpringJUnitConfig(ApplicationConfiguration.class)
@ActiveProfiles(resolver = TestProfileResolver.class)
class EnvironmentAwareTest {
}
~~~

The resolver receives the test class and returns an array of profiles to activate. When a resolver is declared, the static profile list in the annotation's `profiles` attribute is no longer the primary selection source; the resolver is responsible for returning the final list.

A custom resolver is useful when there is a shared rule across a group of tests. However, if the resolver depends on environment variables of individual machines, tests can become hard to reproduce and the context cache may create many different configurations. Prefer explicit profiles for typical tests and use a resolver only when genuinely needed.

## 8. Profiles and Profile-Specific Configuration in Spring Boot

Spring Boot can load profile-specific configuration files. For example:

~~~text
src/main/resources/
  application.yml
  application-test.yml
  application-development.yml
  application-production.yml
~~~

The default file contains shared configuration:

~~~yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
~~~

The `application-test.yml` file contains configuration for tests:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders-test
    username: sa
    password:

app:
  notifications:
    enabled: false
~~~

When the `test` profile is active, Spring Boot loads the default configuration along with configurations for that profile according to Config Data rules. Tests can activate the profile using:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTest {
}
~~~

There is no need to re-declare `spring.profiles.active` inside `application-test.yml` to activate that profile itself. Activate the profile from the launch environment, test annotation, or an appropriate activation mechanism. Profile-controlling properties such as `spring.profiles.active` and `spring.profiles.default` must not be declared in configuration documents that are only activated when another profile is already active.

Spring Boot also supports profile groups. An aggregate profile can activate multiple smaller profiles:

~~~yaml
spring:
  profiles:
    group:
      integration:
        - test
        - postgres
        - messaging
~~~

When `integration` is activated, its member profiles are also activated. This approach is useful when a group of integration tests always requires the same set of database and messaging configurations.

Profile groups are a Spring Boot feature. With plain Spring Framework, `Environment` and `@Profile` still work, but file loading behavior and conveniences like profile groups belong to Boot's configuration layer.

## 9. Distinguishing Profiles from Properties and Conditional Beans

A profile is a condition based on an environment group. A property is a specific configuration value. The two mechanisms can work together, but they do not replace each other.

Profile example:

~~~java
@Bean
@Profile("test")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}
~~~

Property example in Spring Boot:

~~~java
@Bean
@ConditionalOnProperty(
    name = "payment.gateway.enabled",
    havingValue = "true"
)
PaymentGateway paymentGateway() {
    return new HttpPaymentGateway();
}
~~~

`@ConditionalOnProperty` checks a property value; it is not a core Spring Framework annotation, but a Spring Boot conditional utility.

Some ways to choose configuration:

| Need | Suitable Mechanism |
|---|---|
| Select a group of beans for test or production | `@Profile` |
| Enable/disable a feature by property | `@ConditionalOnProperty` |
| Select beans by type and qualifier | `@Qualifier`, `@Primary` |
| Custom condition based on Environment or classpath | Custom `Condition` |
| Profile-specific configuration in Boot | `application-{profile}.yml` |

Avoid creating a new profile for every small flag if it is merely a property. A profile should represent an environment or a meaningful configuration set, while a feature flag should use a property or a feature management mechanism.

## 10. Selecting a Unique Bean and Avoiding Conflicts

When injecting by interface, Spring needs to determine the matching bean. If profiles activate multiple implementations of the same type, injection can become ambiguous.

Example of two active beans:

~~~java
@Component
@Profile("test")
class FakePaymentGateway implements PaymentGateway {
}

@Component
@Profile("local")
class LocalPaymentGateway implements PaymentGateway {
}
~~~

If a test activates both `test` and `local`, both beans may be registered. When a service requests a `PaymentGateway` without a precedence rule, Spring may fail due to multiple candidates.

There are several options:

- Design profiles so that only one implementation per boundary is registered.
- Use `@Primary` on the default bean when multiple candidates are valid.
- Use `@Qualifier` when a consumer needs a specific implementation.
- Use explicit bean names in configurations and injection points.
- Separate configuration classes so each environment has the appropriate set of beans.

Qualifier example:

~~~java
@Configuration
class GatewayConfiguration {

    @Bean
    @Profile("test")
    @Qualifier("testGateway")
    PaymentGateway testGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("production")
    @Qualifier("productionGateway")
    PaymentGateway productionGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

In cases where each environment has only one matching bean, qualifiers are usually unnecessary. Avoid adding `@Qualifier` or `@Primary` merely to mask the fact that multiple profiles were activated unexpectedly.

## 11. Structuring Test Profiles to Avoid Machine Dependence

A reliable test needs to declare its own environment. If a test only passes when a developer's machine has a special environment variable set, results may differ on CI or a teammate's machine.

A common structure:

~~~text
src/test/java/
  com/example/
    BaseIntegrationTest.java
    OrderServiceIntegrationTest.java

src/test/resources/
  application-test.yml
~~~

Base test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}
~~~

Inheriting test:

~~~java
class OrderServiceIntegrationTest extends BaseIntegrationTest {

    @Autowired
    OrderService orderService;

    @Test
    void placesOrder() {
        // Test uses the test profile declared on the base class.
    }
}
~~~

Some useful principles:

- Declare test profiles on test classes or a clearly scoped base class.
- Place test properties in `src/test/resources` when appropriate.
- Do not let production endpoints, passwords, or secrets leak into test configs.
- Use dedicated databases, embedded databases, or Testcontainers depending on the boundary under test.
- Do not depend on profiles set in the runner's shell.
- When needing to test different profiles, create separate test classes with explicit configurations.
- Do not share one test profile for every purpose if unit tests and integration tests have different resource needs.

If a test needs to verify production configuration, test bean conditions or configuration using an isolated test context. Do not boot the application with production credentials just to prove that the production profile selects the right implementation.

## 12. Observing Active Profiles and Beans

When unsure which profiles are active, you can inspect `Environment` in a test:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "integration"})
class ActiveProfileInspectionTest {

    @Autowired
    Environment environment;

    @Test
    void activatesExpectedProfiles() {
        assertArrayEquals(
            new String[] {"test", "integration"},
            environment.getActiveProfiles()
        );
    }
}
~~~

You can check the selected beans:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void registersTheExpectedGateway() {
    assertTrue(
        applicationContext.containsBean("testPaymentGateway")
    );
    assertFalse(
        applicationContext.containsBean("productionPaymentGateway")
    );
}
~~~

The default bean name from `@Bean` is usually the factory method name. For components, the default bean name is usually based on the class name following Spring's bean naming rules. When you need to check a specific bean, give it an explicit name in the configuration so the test does not rely on guesswork.

When debugging a context, you can log active profiles:

~~~java
System.out.println(
    Arrays.toString(environment.getActiveProfiles())
);
~~~

In Spring Boot, Actuator provides `environment` and `beans` endpoints to aid diagnostics when securely configured, though sensitive configuration details should not be exposed publicly.

## 13. How Profiles Affect the ApplicationContext Cache

Spring TestContext caches contexts based on configuration metadata. The list of active profiles is part of the context configuration and affects the cache key.

Example:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class TestProfileContextTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileContextTest {
}
~~~

These two test classes have different active profiles and therefore normally require two separate contexts. This is necessary because the set of beans and properties may differ.

If a suite declares many distinct profile combinations, Spring must load many contexts and runtime may increase. Standardize test class configurations when they genuinely need the same environment. Do not merge profiles just to increase cache hits if doing so causes tests to use the wrong beans or resources.

Dynamic profile resolvers can also cause the context key to vary depending on their return values. If a resolver reads a system property, ensure tests do not mutate that value between context creations in confusing ways.

## 14. Common Pitfalls

- **Forgetting `@ActiveProfiles("test")`:** the test may use the default profile or a profile from the host environment, causing test beans not to be registered.
- **Assuming `@Profile` activates a profile by itself:** this annotation only sets a bean registration condition; the test or launch environment must activate the profile.
- **Activating multiple implementations simultaneously:** Spring may find multiple beans of the same type and not know which one to inject.
- **Placing `spring.profiles.active` in a profile-specific file:** profile activation configuration must be placed in an appropriate configuration source, not in a document loaded only after a profile is already active.
- **Unintended profile inheritance:** `inheritProfiles` defaults to true; subclasses may receive extra profiles from a base class.
- **Using a resolver dependent on a personal machine:** tests may produce different results between local and CI.
- **Using profiles for every feature flag:** profiles should represent environment groups; properties are more suitable for toggling individual features.
- **Treating profiles as a security mechanism:** profiles only select configurations and beans; they do not protect secrets or endpoints.
- **Using `@Primary` to mask profile conflicts:** understand why multiple beans are registered together before setting priority order.
- **Starting production integrations in tests:** verify production configuration using an isolated context rather than connecting to real production resources.

## 15. Workflow for Selecting Beans by Test Environment

When you need a dedicated implementation for tests, follow this sequence:

1. Identify the interface or boundary that the application needs to swap by environment.
2. Write the test implementation and the implementation for the real runtime environment.
3. Place the `@Profile` condition on the corresponding component or bean factory method.
4. Activate the test profile with `@ActiveProfiles` on the test class or base class.
5. If there are multiple profiles, clearly determine whether they are combined or replaced via `inheritProfiles`.
6. Initialize a minimal context or application test context according to the required scope.
7. Inject via the interface and verify the selected bean or observable behavior.
8. Inspect active profiles when diagnosing configuration issues.
9. Ensure tests do not depend on environment variables or secrets of a personal machine.
10. Add dynamic resolvers or profile groups only when the environment structure genuinely requires them.

## Conclusion

`@ActiveProfiles` tells Spring TestContext which profiles to activate when loading the context for a test. `@Profile` uses that condition to decide which components, configuration classes, or bean factory methods are registered. As a result, the same service can receive a fake adapter in tests and an implementation connected to real systems in deployment.

Declare test profiles explicitly, keep the set of matching beans unambiguous, and distinguish profiles from properties. By understanding profile inheritance and context caching, you can organize environment-specific tests in a reproducible, diagnosable manner that is independent of host machine configuration.


