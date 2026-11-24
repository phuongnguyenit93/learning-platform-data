# Profile Inheritance and ActiveProfilesResolver

Spring Profiles allow an application to select beans and configurations suited to each environment or execution purpose. In testing, profiles determine which components are loaded into the `ApplicationContext`, such as configurations using a test database, mock services, or beans dedicated to integration tests.

The Spring TestContext Framework provides the `@ActiveProfiles` annotation to declare profiles for a test class. When test classes have an inheritance relationship, Spring can combine profiles from the parent and child classes. If the default combination is unsuitable, the `inheritProfiles` attribute allows replacing inherited profiles. For cases where profiles need to be chosen based on the environment or custom rules, `ActiveProfilesResolver` allows determining the profile list programmatically.

## 1. What Role Do Profiles Play in Spring?

A profile is a name representing a group of beans or configurations. A component marked with `@Profile` is only registered when the corresponding profile is active.

Example:

```java
@Configuration
@Profile("test")
class TestDataConfiguration {

    @Bean
    DataSource dataSource() {
        return createTestDataSource();
    }
}
```

The configuration above is used only when the `test` profile is active. Another configuration can provide a DataSource for the development environment:

```java
@Configuration
@Profile("dev")
class DevelopmentDataConfiguration {

    @Bean
    DataSource dataSource() {
        return createDevelopmentDataSource();
    }
}
```

The `createTestDataSource()` and `createDevelopmentDataSource()` methods in the example are omitted initialization details to focus on the profile condition.

It is important to distinguish the two annotations:

- `@Profile` is placed on a configuration or bean to decide whether that component is registered.
- `@ActiveProfiles` is placed on a test class to declare the profiles Spring should activate when creating the test context.

For example, a test class can activate `test`, while a `@Profile("test")` configuration provides the appropriate beans for that test.

## 2. Declaring Profiles with @ActiveProfiles

`@ActiveProfiles` can be used on a test class:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.createOrder(
                new CreateOrderCommand("CUSTOMER-42")
        );

        assertNotNull(order.getId());
    }
}
```

In this example:

1. `@SpringBootTest` instructs Spring Boot to create an application context for the integration test.
2. `@ActiveProfiles("test")` declares the `test` profile for the test context.
3. Spring loads the beans and configurations matching the active profile.
4. The test uses the bean injected from the context.

With Spring Boot applications, the `test` profile is often used to select configurations in `application-test.properties` or `application-test.yml`. Those configurations can specify a test database, internal endpoints, or properties suitable for testing.

Example:

```yaml
# application-test.yml
spring:
  datasource:
    url: jdbc:h2:mem:orders-test
    username: sa
    password:
```

This is an illustrative example; specific dependencies and database configurations depend on the project. Do not put production passwords or connection details into test configuration files.

If a test needs multiple profiles, you can declare a list:

```java
@ActiveProfiles({"test", "stub-payment"})
class CheckoutIntegrationTest {
    // ...
}
```

Both `test` and `stub-payment` are activated. A bean can be restricted using a single profile or a profile expression depending on configuration needs.

## 3. How Are Profiles Inherited Across Test Classes?

When a test class extends another test class, the Spring TestContext Framework by default allows inheriting the profiles declared on the parent class. If the child class also declares `@ActiveProfiles`, the profiles from the parent and child classes are combined.

Example:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
    // Shared configuration and behavior for integration tests
}

@ActiveProfiles("database")
class CustomerRepositoryTest extends BaseIntegrationTest {
    // Tests the repository
}
```

With the default `inheritProfiles = true`, the `CustomerRepositoryTest` class has both profiles:

```text
BaseIntegrationTest
    @ActiveProfiles("integration")
              |
              v
CustomerRepositoryTest
    @ActiveProfiles("database")
              |
              v
Active profiles of the test context:
    integration
    database
```

This combination is useful when the parent class defines shared profiles for a group of tests, while the child class adds specialized profiles. For example, all integration tests use the `integration` profile, while repository tests add `database` and payment tests add `payment-stub`.

If the child class does not declare `@ActiveProfiles`, profiles found on the parent class can still be used. The inheritance mechanism helps avoid repeating the same declaration across multiple test classes.

### Multi-level inheritance

Profiles can be combined across multiple classes in an inheritance chain:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@ActiveProfiles("database")
abstract class BaseRepositoryTest extends BaseIntegrationTest {
}

@ActiveProfiles("postgres-test")
class CustomerRepositoryTest extends BaseRepositoryTest {
}
```

With the default inheritance policy, the context of `CustomerRepositoryTest` receives the profiles declared across the class hierarchy:

```text
BaseIntegrationTest       -> integration
BaseRepositoryTest        -> database
CustomerRepositoryTest    -> postgres-test
                           ----------------
Active profiles           -> integration, database, postgres-test
```

This organization fits when each class level represents a clear configuration scope. However, avoid creating many inheritance layers just to accumulate profiles. If each test class's profiles are easier to understand when declared directly, a simpler structure is usually easier to maintain.

## 4. Disabling Inheritance with inheritProfiles = false

There are cases where a child class needs an independent set of profiles. For example, the parent class uses an integrated database configuration, while the child class tests a completely different configuration and must not activate the parent class's profiles.

In that case, set `inheritProfiles = false`:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false
)
class IsolatedConfigurationTest extends BaseIntegrationTest {
    // Uses only the isolated profile
}
```

The profiles of `IsolatedConfigurationTest` consist only of `isolated`. The parent class's `integration` profile is not merged into the child class's context.

This can be represented as:

```text
BaseIntegrationTest
    @ActiveProfiles("integration")
              |
              v
IsolatedConfigurationTest
    @ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false
    )
              |
              v
Active profiles:
    isolated
```

`inheritProfiles = false` applies at the child class's `@ActiveProfiles` declaration. It controls whether profiles from the parent class are merged into the current class's list.

Use this attribute when configuration separation is genuinely needed. Disabling inheritance arbitrarily can cause the child class to lose shared profiles that test beans or configurations still depend on.

## 5. Can @ActiveProfiles Combine with Profiles from Other Sources?

When building the test context, Spring needs a specific list of profiles before loading profile-dependent beans. This list can come from `@ActiveProfiles` or from a resolver specified on the annotation.

In ordinary tests, you should explicitly declare the required profiles so results do not depend on the environment configuration of the machine running the test. For example:

```java
@ActiveProfiles("test")
@SpringBootTest
class CustomerServiceTest {
    // ...
}
```

This makes the test's intent visible right in the source code. When a test needs different profiles, they can be declared separately or via a resolver.

Do not confuse `@ActiveProfiles` with setting `spring.profiles.active` in a configuration file or an environment variable for the entire process. `@ActiveProfiles` is Spring TestContext metadata for a test class and is used when Spring determines profiles for the test context. If a test class declares this annotation, Spring uses the profiles determined from the annotation or corresponding resolver to create the context. When you need to control profiles via an external rule, express that rule using `ActiveProfilesResolver` instead of assuming an environment variable will automatically override the annotation.

## 6. What Is ActiveProfilesResolver?

`ActiveProfilesResolver` is an interface of the Spring TestContext Framework. It allows a test to programmatically determine the list of profiles to activate.

The interface has the method:

```java
public interface ActiveProfilesResolver {

    String[] resolve(Class<?> testClass);
}
```

Spring passes the current test class into `resolve`. The resolver returns an array of profile names. Spring uses that list when creating the test context.

A resolver is suitable when profiles depend on:

- System properties passed from the test command.
- Environment variables provided by CI.
- Conventions based on package or test class type.
- Custom annotations on the test class.
- A project-specific configuration selection rule.

The resolver should only perform profile resolution. It should not initialize an application context or depend on beans within the context, because profiles must be determined before the context is created.

## 7. Writing a Simple Resolver

For example, a project wants to allow passing a profile via the `test.profile` system property. If not passed, the test uses the `test` profile.

Create the resolver:

```java
import org.springframework.test.context.ActiveProfilesResolver;

public class TestProfileResolver implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String profile = System.getProperty("test.profile");

        if (profile == null || profile.isBlank()) {
            return new String[] {"test"};
        }

        return new String[] {profile.trim()};
    }
}
```

Register the resolver on the test class:

```java
@SpringBootTest
@ActiveProfiles(resolver = TestProfileResolver.class)
class CustomerServiceTest {
    // ...
}
```

When running the test without passing the system property, the resolver returns `test`. When passing `-Dtest.profile=integration`, the resolver returns `integration`.

Example running with Gradle:

```bash
./gradlew test -Dtest.profile=integration
```

Depending on how Gradle and the project's test task are configured, the system property may need to be forwarded to the test JVM. You can configure the `Test` task to pass the property explicitly if the Gradle JVM and test JVM are separate processes.

Example Groovy configuration:

```groovy
tasks.withType(Test).configureEach {
    systemProperty "test.profile",
            System.getProperty("test.profile", "test")
}
```

This is an illustrative configuration. The project should place it in the appropriate build script and task scope according to the existing build structure.

## 8. Resolvers Can Be Based on Environment Variables

If CI or the test execution environment manages configuration via environment variables, the resolver can read that variable:

```java
import org.springframework.test.context.ActiveProfilesResolver;

public class EnvironmentProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String profile = System.getenv("TEST_PROFILE");

        if (profile == null || profile.isBlank()) {
            return new String[] {"test"};
        }

        return new String[] {profile.trim()};
    }
}
```

Register:

```java
@ActiveProfiles(resolver = EnvironmentProfilesResolver.class)
class CustomerRepositoryTest {
    // ...
}
```

When the `TEST_PROFILE` variable does not exist or is blank, the resolver chooses `test`. When the variable is set, the resolver returns the corresponding profile name.

If both system properties and environment variables need to be supported, clearly define the precedence order:

```java
public class EnvironmentProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String profile = System.getProperty("test.profile");

        if (profile == null || profile.isBlank()) {
            profile = System.getenv("TEST_PROFILE");
        }

        if (profile == null || profile.isBlank()) {
            profile = "test";
        }

        return new String[] {profile.trim()};
    }
}
```

In this example, the system property takes precedence, followed by the environment variable, and finally the default value. Clear rules help CI and developers understand which profile a given test will select.

Avoid letting a resolver select profiles randomly or depend on uncontrolled machine state. If profiles change without a clear reason, tests may load different contexts between developer machines and CI, making bugs hard to reproduce.

## 9. Why Does a Resolver Receive testClass?

The `testClass` parameter lets the resolver know which class is requesting profiles. Based on the class, the resolver can apply conventions by package, class name, or annotations.

For example, a project might categorize integration tests by package:

```java
public class PackageProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String packageName = testClass.getPackageName();

        if (packageName.contains(".repository.")) {
            return new String[] {"test", "database"};
        }

        if (packageName.contains(".web.")) {
            return new String[] {"test", "web"};
        }

        return new String[] {"test"};
    }
}
```

The resolver is registered as follows:

```java
@ActiveProfiles(resolver = PackageProfilesResolver.class)
@SpringBootTest
class CustomerRepositoryIntegrationTest {
    // ...
}
```

A test class in a package whose name contains `.repository.` will also receive the `database` profile. A test in a `.web.` package will also receive the `web` profile.

This is an example of a project organization convention. If package names are not a stable contract, renaming a package could unintentionally change profiles. In that case, explicit declarations or custom annotations may be safer and easier to read.

A resolver can also inspect custom annotations:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DatabaseTest {
}
```

```java
public class AnnotationProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        if (testClass.isAnnotationPresent(DatabaseTest.class)) {
            return new String[] {"test", "database"};
        }

        return new String[] {"test"};
    }
}
```

This approach fits when a project has several test categories classified by metadata. However, if there are only a few test classes, declaring `@ActiveProfiles` directly is usually simpler than creating additional annotations and resolvers.

## 10. Resolvers and Profile Inheritance

A resolver participates in determining profiles for a test class that declares `@ActiveProfiles(resolver = ...)`. After the resolver returns the list for that class, the Spring TestContext Framework handles the inheritance policy according to `inheritProfiles`.

Example:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@ActiveProfiles(
        resolver = TestProfileResolver.class,
        inheritProfiles = true
)
class CustomerRepositoryTest extends BaseIntegrationTest {
}
```

In this case:

- The resolver determines the profiles for `CustomerRepositoryTest`.
- Because `inheritProfiles = true`, profiles from the parent class are combined according to the inheritance policy.
- The child class context receives the profiles returned by the resolver along with the profiles inherited from the parent class.

If the child class does not need profiles from the parent class:

```java
@ActiveProfiles(
        resolver = TestProfileResolver.class,
        inheritProfiles = false
)
class IsolatedConfigurationTest extends BaseIntegrationTest {
}
```

Then the child class's profile list is determined by the resolver, without merging inherited profiles from `BaseIntegrationTest`.

When specifying a resolver, the profile list returned by the resolver is the source for determining profiles for that declaration; do not expect values written in `profiles` to also be automatically added to the resolver's result. Keep all necessary rules inside the resolver or the chosen inheritance policy, so readers do not misunderstand the actual profile source.

## 11. Resolvers Should Be Deterministic and Easy to Control

A resolver is invoked while Spring determines profiles before building the context. Therefore, code inside a resolver should be small, clear, and produce stable results.

A good resolver typically has these characteristics:

- Returns a non-null array of profiles.
- Only returns valid profile names defined by the project.
- Has a clear default value when external configuration does not exist.
- Has a specific precedence order if reading multiple configuration sources.
- Does not access databases, HTTP services, or beans in the ApplicationContext.
- Does not depend on time or random data.
- Can explain why a given test class receives a certain list of profiles.

Avoid building resolvers so complex that readers must debug multiple layers just to know which profiles the context will initialize with. If the profile is simply `test` for all test classes, `@ActiveProfiles("test")` directly is easier to understand.

### Testing a resolver with unit tests

A resolver is a regular Java class, so it can be tested independently with JUnit:

```java
class TestProfileResolverTest {

    private final TestProfileResolver resolver =
            new TestProfileResolver();

    @Test
    void usesTestProfileWhenPropertyIsMissing() {
        // Need to control the property in the test environment
        String[] profiles = resolver.resolve(CustomerServiceTest.class);

        assertArrayEquals(new String[] {"test"}, profiles);
    }
}
```

The example above only illustrates the test goal. Because system properties are global JVM state, real tests need to save and restore the old value in a `try/finally` block or use a system property management library. Do not let a test mutate a property and affect other tests.

If a resolver reads environment variables, controlling them in unit tests is usually harder because environment variables cannot be modified directly in a portable way in the JVM. You can extract configuration reading into a small component that accepts values as parameters, then test the resolver with mock data or test the profile selection rule through a pure function.

## 12. Profiles and the Spring TestContext Cache

The list of active profiles is part of the configuration used by the Spring TestContext Framework when building and caching the `ApplicationContext`. Two test classes with equivalent context configurations can share a cached context. If profiles differ, Spring usually has to create separate contexts because the set of beans and configuration properties may differ.

Example:

```java
@SpringBootTest
@ActiveProfiles("test")
class CustomerServiceTest {
}

@SpringBootTest
@ActiveProfiles("test", "stub-payment")
class CheckoutServiceTest {
}
```

The two test classes have different profiles. The payment test's context may load additional beans or configurations belonging to the `stub-payment` profile, so the two contexts cannot automatically be treated as identical.

A resolver that selects profiles based on environment variables or system properties can also cause different runs to create different contexts. This can increase the number of contexts in the cache and the test suite runtime. Keep the profile set stable during a run and change it only when the test goal truly requires it.

Context caching does not replace test data management. Profiles determine which configurations and beans are loaded; transactions, fixtures, database cleanup, and mutable state still need separate strategies.

## 13. Combining @ActiveProfiles with @TestPropertySource and Spring Boot Properties

Profiles select the group of configurations and beans to activate. `@TestPropertySource` has a different role: adding or overriding property sources for tests.

Example:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "feature.checkout.enabled=true",
        "checkout.retry-limit=1"
})
class CheckoutServiceTest {
    // ...
}
```

In this example, the `test` profile selects environment-based configuration, while `@TestPropertySource` provides two specific properties for the test class.

You can use a dedicated properties file:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(locations = "classpath:/checkout-test.properties")
class CheckoutServiceTest {
    // ...
}
```

Do not use profiles to replace every property override. If you only need to change one or two values in a test class, `@TestPropertySource` can express that intent more directly. If you need to select a group of beans/configurations by environment, profiles are more appropriate.

## 14. Common Pitfalls with Profile Inheritance and Resolvers

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Child test class activates parent class profiles too | `inheritProfiles` defaults to `true` | Check `@ActiveProfiles` declarations on parent classes |
| Child test class loads unwanted profiles | Child class inherits profiles unintentionally | Set `inheritProfiles = false` when separation is needed |
| Resolver returns wrong profiles | Rules for reading system properties/environment are unclear | Check precedence order and default value |
| Resolver is not invoked | Annotation does not specify resolver or test uses other context metadata | Check `@ActiveProfiles(resolver = ...)` on the test class |
| Profiles in `profiles` do not appear as expected | A custom resolver is determining the profile list | Include needed profiles in the resolver result or use direct declaration |
| Bean is not registered | Profile name does not match the `@Profile` condition | Check profile names and bean configuration |
| Tests behave differently between local and CI | Resolver depends on different environments | Document configuration sources and set stable CI values |
| Context is created multiple times | Multiple profile lists produce different context configurations | Check profiles and metadata of the test classes |
| Tests are affected by other tests | Mutable data or global properties are not restored | Clean up state and manage properties within test scope |

When profiles are not as expected, examine the final profile list used by the context, which class declares the annotation, whether the inheritance policy is enabled, and what the resolver returns. Only then check the beans with corresponding `@Profile` conditions.

## 15. How to Choose Between Static Declaration and a Resolver

Not every test class needs an `ActiveProfilesResolver`. You can choose based on how dynamic the profiles are:

| Need | Appropriate Approach |
|---|---|
| All tests in the class use a fixed profile | `@ActiveProfiles("test")` |
| Child class adds to shared parent class profiles | Default inheritance with `inheritProfiles = true` |
| Child class needs an independent set of profiles | `inheritProfiles = false` |
| Profiles are determined by system property or environment variable | Custom `ActiveProfilesResolver` |
| Profiles depend on conventions by test class type | Resolver inspecting metadata or package |
| Only need to change a few properties in one test class | Consider `@TestPropertySource` |

Prefer static declarations when profiles are known in advance and do not need to change by environment. A resolver is valuable when there truly is a profile selection rule that needs to be shared or depends on runtime data.

Profile inheritance helps share common configurations among test classes in a parent-child relationship. `inheritProfiles = false` allows a child class to opt out of that configuration. `ActiveProfilesResolver` provides a profile list according to a programmable rule. When these three mechanisms are used intentionally, the test context is initialized with the right group of beans and properties, and readers can trace the origin of every profile when diagnosing errors.

