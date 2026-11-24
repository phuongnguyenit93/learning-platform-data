# Activating Test Profiles with @ActiveProfiles in Spring Boot

In Spring Boot, **profiles** let an application vary configuration and beans by environment: `dev`, `test`, `staging`, `prod`, or domain-specific names. During integration testing, we generally want an `ApplicationContext` distinct from production: low-risk settings, mock/fake adapters, test databases, and short timeouts—while keeping most Spring wiring intact to verify real behavior.

The Spring TestContext Framework's **`@ActiveProfiles`** annotation solves this need: it declares which **bean definition profiles** should be activated when Spring loads the `ApplicationContext` for a test class.

Simple example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTest {

    @Test
    void contextLoads() {
        // Spring initializes the context with the "test" profile.
    }
}
~~~

When standard Spring Boot configuration loads, profile `test` also causes **`application-test.yml`** or **`application-test.properties`** to be picked up by Config Data. This lets tests use dedicated settings without modifying `application.yml` meant for the application.

This lesson uses **Spring Boot 3.3.x, Spring Framework 6.1.x, JUnit Jupiter, and Java 21**. It distinguishes test profiles from property overrides, walks through complete examples, covers profile inheritance, profile resolvers, interactions with the TestContext cache, test slices, and common pitfalls.

## 1. What Problem Does @ActiveProfiles Solve?

Suppose an e-commerce application has two notification adapters:

- `SmtpNotificationSender`: sends real SMTP emails in certain environments.
- `FakeNotificationSender`: stores events in memory without sending external emails.

Production configuration might also point to live payment gateways or external queues. If tests boot with the wrong profile, they risk calling real systems, requiring production credentials, or dispatching unintended traffic.

With `@ActiveProfiles("test")`, tests select beans dedicated to the test profile and load test-environment properties.

~~~text
Test class
  |
  +-- @SpringBootTest
  |
  +-- @ActiveProfiles("test")
              |
              v
     Spring TestContext Framework
              |
              v
       ApplicationContext
              |
              +-- @Profile("test") beans
              +-- @Profile("!test") beans excluded
              +-- application.yml
              +-- application-test.yml
              |
              v
       Test assertions
~~~

**Distinction:** `@ActiveProfiles` only declares profiles for a **context loaded by Spring TestContext**. A plain unit test creating Java objects via `new` without starting a Spring context gets no effect from adding this annotation.

## 2. Package, Dependencies, and Scope

Correct import:

~~~java
import org.springframework.test.context.ActiveProfiles;
~~~

This annotation belongs to **spring-test**, included via `spring-boot-starter-test` in standard Spring Boot applications.

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### Gradle Groovy DSL

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### Gradle Kotlin DSL

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

In a Spring Boot 3.3 project, Spring TestContext integrates with JUnit Jupiter through its extension mechanism. `@SpringBootTest` already declares the necessary Spring integration; you do not need to add `@ExtendWith(SpringExtension.class)` separately here.

`@ActiveProfiles` is applied at the **class level**. It can sit on a test class or meta-annotation and inherits according to TestContext rules. Do not place it on a test method expecting each method in the same class to spin up a context with a different profile.

## 3. Minimal Example with @SpringBootTest

Main application:

~~~java
package com.example.profiledemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
~~~

File `src/main/resources/application.yml`:

~~~yaml
app:
  greeting:
    message: "Hello from default configuration"
    max-retries: 3
~~~

File `src/test/resources/application-test.yml`:

~~~yaml
app:
  greeting:
    message: "Hello from test configuration"
    max-retries: 1
~~~

Configuration class:

~~~java
package com.example.profiledemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.greeting")
public record GreetingProperties(
        String message,
        int maxRetries) {
}
~~~

Register this class via `@ConfigurationPropertiesScan` on `ProfileDemoApplication`, for example:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ProfileDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
~~~

Matching imports:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
~~~

Test:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.profiledemo.config.GreetingProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class GreetingPropertiesTest {

    @Autowired
    GreetingProperties greeting;

    @Test
    void usesTestProfileConfiguration() {
        assertThat(greeting.message())
                .isEqualTo("Hello from test configuration");
        assertThat(greeting.maxRetries()).isEqualTo(1);
    }
}
~~~

**What happens:**

1. JUnit discovers the test.
2. Spring TestContext builds the merged test context configuration.
3. `@ActiveProfiles("test")` activates the `test` profile for that context.
4. Spring Boot loads Config Data and applies documents matching the test profile.
5. `GreetingProperties` binds from the effective values.
6. Assertions verify the test-specific values.

Unless overridden by a higher-precedence source, `application-test.yml` overrides matching keys from `application.yml`.

### Important File Locations

~~~text
src/
├── main/
│   ├── java/com/example/profiledemo/
│   │   ├── ProfileDemoApplication.java
│   │   └── config/GreetingProperties.java
│   └── resources/
│       └── application.yml
└── test/
    ├── java/com/example/profiledemo/
    │   └── GreetingPropertiesTest.java
    └── resources/
        └── application-test.yml
~~~

`src/test/resources` sits on the test classpath and is normally excluded from the production JAR packaged from `src/main`. This neatly isolates test configuration.

## 4. @ActiveProfiles and @Profile Working Together

`@Profile` makes bean registration conditional. `@ActiveProfiles` selects profiles for the test context, deciding which beans match.

Interface definition:

~~~java
package com.example.profiledemo.notification;

public interface NotificationSender {
    void send(String recipient, String message);
    String kind();
}
~~~

Real bean:

~~~java
package com.example.profiledemo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("!test")
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("Send to " + recipient + ": " + message);
    }

    @Override
    public String kind() {
        return "console";
    }
}
~~~

Test bean:

~~~java
package com.example.profiledemo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("test")
public class FakeNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        // Does not open SMTP or HTTP connections.
    }

    @Override
    public String kind() {
        return "fake";
    }
}
~~~

Test:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.profiledemo.notification.NotificationSender;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class NotificationProfileTest {

    @Autowired
    NotificationSender sender;

    @Test
    void selectsFakeSender() {
        assertThat(sender.kind()).isEqualTo("fake");
    }
}
~~~

With profile `test`, `FakeNotificationSender` matches while `ConsoleNotificationSender` (`@Profile("!test")`) is excluded.

**Design note:** placing `@Profile("!test")` on a real bean enables it in every environment **without test**, not solely production. If live sending should happen only in a specific profile, use `@Profile("prod")` or explicit feature flags instead of assuming every non-test environment is safe.

## 5. @ActiveProfiles Syntax

Equivalent basic forms:

~~~java
@ActiveProfiles("test")
~~~

~~~java
@ActiveProfiles({"test", "integration"})
~~~

~~~java
@ActiveProfiles(profiles = {"test", "integration"})
~~~

`value` is an alias for `profiles`:

~~~java
@ActiveProfiles(value = "test")
~~~

Never specify both `value` and `profiles` with differing values on the same annotation because they alias each other.

Syntax:

~~~java
@ActiveProfiles(profiles = "test", inheritProfiles = false)
~~~

prevents inheriting profiles from a superclass or enclosing test class. By default `inheritProfiles = true`.

You can specify a custom resolver:

~~~java
@ActiveProfiles(resolver = CiProfileResolver.class)
~~~

to compute profiles programmatically. Resolvers are covered in a later section.

### No Method-Level @ActiveProfiles Syntax

A class like:

~~~java
@SpringBootTest
class CheckoutTest {

    @Test
    @ActiveProfiles("test")
    void localTest() {
    }
}
~~~

is not valid usage because `@ActiveProfiles` targets `TYPE`. When different profile combinations are needed, create **separate test classes**, each declaring its own profile and using a matching context.

## 6. Profiles and Config Data: application-test.yml

Spring Boot commonly evaluates both the base `application.yml` and profile-specific variants, such as:

~~~text
application.yml
application-test.yml
application-integration.yml
application-prod.yml
~~~

When `test` is active, `application-test.yml` is evaluated and can override matching keys from the base file.

Example:

`src/main/resources/application.yml`:

~~~yaml
app:
  client:
    endpoint: https://api.example.org
    timeout: 20s
    retries: 4

logging:
  level:
    com.example.profiledemo: INFO
~~~

`src/test/resources/application-test.yml`:

~~~yaml
app:
  client:
    endpoint: http://127.0.0.1:18080
    timeout: 500ms
    retries: 1

logging:
  level:
    com.example.profiledemo: DEBUG
~~~

`@ActiveProfiles("test")` activates the test profile when loading the context, binding properties to:

~~~text
endpoint = http://127.0.0.1:18080
timeout  = PT0.5S
retries  = 1
~~~

They can still be overridden if the test declares higher-priority properties via `@TestPropertySource`, `@SpringBootTest(properties=...)`, or `@DynamicPropertySource`.

### application-test.yml Does Not Activate Automatically Just Because JUnit Runs

Placing `application-test.yml` in `src/test/resources` is **not enough** to make Spring Boot activate profile `test`. An explicit profile activation mechanism is required, such as `@ActiveProfiles("test")` on integration tests.

Nor does a normally launched application activate profile `test` merely because a file has "test" in its name.

### Do Not Change Profiles with spring.profiles.active Inside Profile-Specific Files

Avoid:

~~~yaml
# application-test.yml — do not write this
spring:
  profiles:
    active: prod
~~~

In Spring Boot's Config Data system, `spring.profiles.active` and `spring.profiles.default` are restricted: they cannot be used inside profile-specific files or documents activated via `spring.config.activate.on-profile`. To activate profiles for tests, put `@ActiveProfiles` on the test class.

## 7. Using @SpringBootTest with Multiple Profiles

When a scenario needs two configuration groups together:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "integration"})
class IntegrationMessagingTest {
    // ...
}
~~~

Both `test` and `integration` become active profiles. Consequently:

- Beans with `@Profile("test")` are eligible.
- Beans with `@Profile("integration")` are eligible.
- Beans with `@Profile({"test", "integration"})` match if at least one listed profile is active.
- Beans with `@Profile("!prod")` match since `prod` is inactive.
- Config Data documents for both profiles participate.

**Do not mistake `@Profile({"test","integration"})` for requiring both profiles simultaneously.** Inside that annotation array, separate strings form an OR condition. To require both simultaneously, Spring supports profile expressions like `@Profile("test & integration")`.

### Does Profile Order Affect Configuration?

It can. When multiple profile-specific files define the same key, Spring Boot applies precedence according to declared profile order and Config Data locations; in typical setups, profiles listed later override earlier ones.

Example:

~~~text
application-test.yml:
  app.feature.limit = 10

application-integration.yml:
  app.feature.limit = 30
~~~

With `@ActiveProfiles({"test", "integration"})`, the typical result is 30 unless a stronger source overrides it. However, imported Config Data, location groups, and custom property sources can also affect outcomes. For tests requiring deterministic values, assert the effective value in `Environment` rather than guessing from filenames alone.

### Never Accidentally Activate prod in Tests

~~~java
@ActiveProfiles({"test", "prod"})
~~~

does not cause `test` to disable `prod`. `@Profile("prod")` beans can still be created, risking production connections or unintended side effects. For isolation, prefer explicit test profiles paired with safe fake/test boundaries.

## 8. Verifying Active Profiles in Tests

To confirm profiles are active, inject `Environment`:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ActiveProfileEnvironmentTest {

    @Autowired
    Environment environment;

    @Test
    void testProfileIsActive() {
        assertThat(environment.getActiveProfiles())
                .contains("test");
    }
}
~~~

With multiple profiles, `getActiveProfiles()` returns a String array. When an exact profile set matters, assert the full array rather than only `contains("test")`.

You can also use:

~~~java
import org.springframework.core.env.Profiles;

assertThat(environment.acceptsProfiles(
        Profiles.of("test"))).isTrue();
~~~

`Profiles.of("test")` is the modern Spring Framework API for evaluating profile expressions.

### Active vs. Default Profiles Differ

`environment.getActiveProfiles()` lists explicitly activated profiles. `environment.getDefaultProfiles()` lists fallback profiles used when **no active profile is set**.

Do not write a test inspecting only default profiles and conclude `@ActiveProfiles("test")` failed. The two lists serve different roles.

### Does spring.profiles.active Always Contain test?

Do not treat `environment.getProperty("spring.profiles.active")` as the sole check for `@ActiveProfiles`. TestContext can apply profiles directly to Environment; that property string is not the single source of truth for active profiles. Use `getActiveProfiles()` or `acceptsProfiles(...)`.

## 9. How @ActiveProfiles Differs from @TestPropertySource

Both annotations have distinct responsibilities:

`@ActiveProfiles`:

~~~java
@ActiveProfiles("test")
~~~

selects profiles for the context, driving `@Profile` conditions and profile-specific Config Data sources.

`@TestPropertySource`:

~~~java
@TestPropertySource(properties = {
        "app.client.timeout=100ms",
        "app.client.retries=0"
})
~~~

injects properties directly into the test environment, typically outranking `application.yml`/`application-test.yml`.

They can be combined:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "app.client.timeout=100ms"
})
class TimeoutOverrideTest {
    // ...
}
~~~

In that setup, the `test` profile remains active while `app.client.timeout` is overridden right on the test class.

### When to Choose Which?

| Need | Appropriate approach |
| --- | --- |
| Swap fake beans for real beans | `@ActiveProfiles("test")` with `@Profile` |
| Load a full test-environment configuration set | `@ActiveProfiles("test")` + `application-test.yml` |
| Change a single value for one scenario | `@TestPropertySource(properties=...)` |
| Change a few values in @SpringBootTest | `@SpringBootTest(properties=...)` |
| Supply dynamically allocated container addresses | `@DynamicPropertySource` |
| Unit test a plain Java object without context | Constructor + fake or mock directly |

### @TestPropertySource Is Not a General YAML Loader

Avoid assuming:

~~~java
@TestPropertySource(
        locations = "classpath:application-test.yml")
~~~

reads YAML identically to Spring Boot Config Data. `@TestPropertySource` handles resource formats differently; in Spring Boot tests, let `application-test.yml` load via **profile-specific Config Data**. Using a custom factory on `@TestPropertySource` in supported versions is a separate design.

## 10. @SpringBootTest(properties=...) with a Test Profile

Spring Boot lets you declare inline properties right on the test annotation:

~~~java
@SpringBootTest(properties = {
        "app.client.timeout=200ms",
        "app.client.retries=1"
})
@ActiveProfiles("test")
class ClientTest {
}
~~~

Here `@ActiveProfiles` still controls the profile, while `properties` supplies overrides for the test-created context.

If `application-test.yml` specifies:

~~~yaml
app:
  client:
    timeout: 1s
    retries: 3
~~~

the inline values from `@SpringBootTest(properties=...)` outrank normal config files, yielding `timeout=200ms` and `retries=1`.

Avoid putting dozens of properties in `application-test.yml` and repeating them in `@SpringBootTest(properties)` without reason. Duplication makes tests harder to maintain because readers cannot tell which place to update when defaults change.

## 11. @DynamicPropertySource and Test Profiles

When using Testcontainers or resources with dynamically assigned ports, connection details are known only after the container starts.

`@DynamicPropertySource` registers supplier callbacks into the Spring TestContext Environment:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest
@ActiveProfiles("test")
class ExternalServiceIntegrationTest {

    // Assume the test manages a server/container via project
    // mechanisms that expose a dynamic endpoint.
    static final String TEST_ENDPOINT = "http://127.0.0.1:18080";

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("app.client.endpoint", () -> TEST_ENDPOINT);
    }
}
~~~

This illustrates the property supplier mechanism; with real Testcontainers, the supplier queries the running container. Never assume port 18080 is listening unless an actual test server is running.

Properties from `@DynamicPropertySource` generally carry **high precedence**, above `@TestPropertySource`, environment/system properties, and regular config files. Thus even if `application-test.yml` sets another endpoint, the dynamic value wins.

`@DynamicPropertySource` does not activate profiles. When you need both fake beans and dynamic endpoints, pair it with `@ActiveProfiles("test")`.

### Caching and Dynamic Resources

If subclasses share a test context configuration while spinning up containers on different endpoints, context caching can feed stale dynamic endpoints into later tests. Spring TestContext recommends considering `@DirtiesContext` when dynamic properties vary across subclasses. Do not overuse `@DirtiesContext` everywhere, however, as it hurts suite performance.

## 12. @ActiveProfiles with @DataJpaTest and Test Slices

Spring Boot provides test slices that load a partial context, such as `@DataJpaTest`, `@WebMvcTest`, and `@JsonTest`. They still run under Spring TestContext, so `@ActiveProfiles` works with them.

Example:

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@ActiveProfiles("test")
class CustomerRepositoryTest {
    // Can @Autowired repositories and test database queries.
}
~~~

`application-test.yml` might supply:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
  datasource:
    url: jdbc:h2:mem:customer-test
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
~~~

**Prerequisite:** include the H2 driver and required JPA dependencies. `@ActiveProfiles("test")` **does not install drivers, create databases, or start containers**.

### @DataJpaTest Has Its Own Database Replacement Behavior

`@DataJpaTest` applies test database auto-configuration that can replace your datasource with an embedded database when conditions match. To test against a real database or container, you may need `@AutoConfigureTestDatabase(replace = ...)` and matching configuration.

Do not assume simply writing `spring.datasource.url` in `application-test.yml` guarantees `@DataJpaTest` always uses that URL.

### @WebMvcTest

~~~java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.ActiveProfiles;

@WebMvcTest(controllers = GreetingController.class)
@ActiveProfiles("test")
class GreetingControllerTest {
    // Can test the controller using MockMvc.
}
~~~

`GreetingController` is a project controller class; depending on its collaborators, the slice test may need mock/fake beans. `@ActiveProfiles` selects the profile without making `@WebMvcTest` load all application services.

## 13. Inheriting @ActiveProfiles from a Superclass

In Spring TestContext, `inheritProfiles = true` by default.

Example:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}
~~~

Subclass:

~~~java
class PaymentServiceTest extends BaseIntegrationTest {
    // Inherits test configuration and the "test" profile.
}
~~~

You do not need to repeat `@ActiveProfiles("test")` on every subclass. This works well for groups of integration tests sharing one environment.

### Subclass Adding a Profile

~~~java
@ActiveProfiles("slow")
class SlowPaymentServiceTest extends BaseIntegrationTest {
}
~~~

Under default rules, the subclass's profiles are appended to the inherited profile list. The context receives both `test` and `slow`.

### Subclass Replacing the Profile List

~~~java
@ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false)
class IsolatedPaymentServiceTest extends BaseIntegrationTest {
}
~~~

With `inheritProfiles = false`, the test class stops inheriting profiles from the superclass (or enclosing class per relevant rules), applying only the declared list.

Be very careful with `inheritProfiles=false`: it can drop the shared `test` profile, re-enabling real beans or skipping `application-test.yml`.

## 14. @Nested Tests and Profile Inheritance

JUnit Jupiter supports `@Nested` for grouping test classes inside an outer test class.

~~~java
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderFlowTest {

    @Test
    void outerCase() {
    }

    @Nested
    class ErrorCases {

        @Test
        void missingCustomer() {
        }
    }
}
~~~

In Spring Framework 6.1, `@ActiveProfiles` is **inherited from enclosing test classes by default**, matching TestContext's nested class support.

However, nested test inheritance can also be customized by TestContext options such as `@NestedTestConfiguration`. If your project customizes test configuration inheritance, verify the actual nested context rather than assuming every annotation applies uniformly.

If a nested class needs its own profile, annotate the nested class with `@ActiveProfiles` and consider `inheritProfiles`. Do not share contexts carelessly across nested tests with differing profile configurations without understanding the test context cache.

## 15. Creating a Composed Annotation for a Test Group

When many tests share identical configuration, define a custom composed annotation combining `@SpringBootTest` and `@ActiveProfiles`:

~~~java
package com.example.profiledemo.testing;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
@ActiveProfiles("test")
public @interface IntegrationTest {
}
~~~

Usage:

~~~java
@IntegrationTest
class CustomerFlowTest {
    // ...
}
~~~

Benefits:

- Avoids repeating both annotations across hundreds of tests.
- Establishes a clear shared convention for integration tests.
- Allows updating the shared profile or test settings in one place.

Avoid nesting too many composed annotations that obscure configuration; for small groups of tests, writing `@SpringBootTest` and `@ActiveProfiles` directly is often clearer.

### Meta-Annotations Still Do Not Guarantee Absolute Safety

If someone adds `@ActiveProfiles("prod")` on a subclass or alters `inheritProfiles`, the active profiles change. Systems with real risk of hitting production still need extra safeguards: fake endpoints, dedicated test credentials, and network controls.

## 16. Selecting Profiles Dynamically with ActiveProfilesResolver

Sometimes profiles must be computed from the test execution environment, such as local vs. CI or backend type.

Spring TestContext provides the SPI:

~~~java
import org.springframework.test.context.ActiveProfilesResolver;
~~~

Implementing a resolver:

~~~java
package com.example.profiledemo.testing;

import org.springframework.test.context.ActiveProfilesResolver;

public final class CiAwareProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String ci = System.getenv("CI");

        if ("true".equalsIgnoreCase(ci)) {
            return new String[] {"test", "ci"};
        }

        return new String[] {"test"};
    }
}
~~~

Usage:

~~~java
@SpringBootTest
@ActiveProfiles(resolver = CiAwareProfilesResolver.class)
class CustomerIntegrationTest {
}
~~~

When environment variable `CI=true`, the resolver selects `test` and `ci`. Otherwise it selects only `test`.

This is an **illustrative example** of profile computation. In real projects, environment-dependent profiles can cause tests to behave differently on laptops vs. CI. Prefer **deterministic** profiles whenever possible; where variation is required, document it clearly in the CI pipeline.

### Using a Resolver Instead of Implicitly Reading spring.profiles.active

In Spring TestContext, when `@ActiveProfiles` is declared, `spring.profiles.active` from environment variables or JVM system properties is **not automatically consulted** to override the test's profile list by default. If you want CLI/system properties to override declared profiles, write an explicit `ActiveProfilesResolver`.

Conceptual example:

~~~java
import org.springframework.core.env.AbstractEnvironment;
import org.springframework.test.context.support.DefaultActiveProfilesResolver;
import org.springframework.util.StringUtils;

public final class SystemPropertyProfilesResolver
        extends DefaultActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String value = System.getProperty(
                AbstractEnvironment.ACTIVE_PROFILES_PROPERTY_NAME);

        if (StringUtils.hasText(value)) {
            return StringUtils.commaDelimitedListToStringArray(
                    StringUtils.trimAllWhitespace(value));
        }

        return super.resolve(testClass);
    }
}
~~~

Registering this class via:

~~~java
@ActiveProfiles(
        profiles = "test",
        resolver = SystemPropertyProfilesResolver.class)
~~~

lets `-Dspring.profiles.active=ci` make the resolver return `ci` instead of `test`. This builds on `DefaultActiveProfilesResolver` and reads the JVM property explicitly; no such override happens automatically with plain `@ActiveProfiles("test")`.

**Warning:** allowing external overrides of test profiles can push tests into unsafe environments. Only enable this if truly required operationally.

## 17. @ActiveProfiles vs. spring.profiles.active: Understanding the Order

In a standard application launch:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

activates profile `prod` through the Environment/Config Data pipeline.

In a **Spring integration test**, if the test class has:

~~~java
@ActiveProfiles("test")
~~~

Spring TestContext uses the annotation to determine the context's profiles; do not expect `SPRING_PROFILES_ACTIVE=prod` to replace `test` automatically under default TestContext behavior.

Both mechanisms shape the Spring Environment, yet follow different configuration paths:

| Context | Typical mechanism |
| --- | --- |
| Running production JAR | `spring.profiles.active` via env/CLI |
| TestContext integration test | `@ActiveProfiles` |
| Tests needing computed profiles | `ActiveProfilesResolver` |
| Unit tests without a Spring context | No Spring profiles used |

Key rule: check `Environment.getActiveProfiles()` inside tests to verify active profiles rather than inferring from a property string in the system environment.

## 18. Profile Groups and Test Profiles

Spring Boot supports `spring.profiles.group` to expand a single profile name into related profiles.

Example in `application.yml`:

~~~yaml
spring:
  profiles:
    group:
      integration:
        - test
        - database
~~~

When profile `integration` is activated in a Spring Boot Config Data flow supporting group expansion, grouped profiles `test` and `database` activate alongside it.

This is convenient for bundling settings, yet makes the actual active profile list longer than what appears on the test annotation.

~~~java
@ActiveProfiles("integration")
~~~

Do not assume from this single string that only `integration` is active at every stage. Inspect `environment.getActiveProfiles()` at runtime and test matching beans/profile-specific properties.

**Config Data restriction:** `spring.profiles.group` is a profile-activation property and must appear in valid locations, never inside profile-specific files like `application-test.yml` or documents gated by `spring.config.activate.on-profile`.

If you simply need two fixed profiles, `@ActiveProfiles({"test","database"})` is often clearer than creating a group.

## 19. Using Profile-Based Multi-Document YAML

Instead of creating `application-test.yml`, you can declare multiple documents in one `application.yml`:

~~~yaml
app:
  message: "default"

---
spring:
  config:
    activate:
      on-profile: test

app:
  message: "from test document"
~~~

With `@ActiveProfiles("test")`, the second document activates.

Notes:

- `spring.config.activate.on-profile` gates a **document** in Config Data.
- `@ActiveProfiles` chooses **profiles** for the test context.
- `@Profile` gates **bean definitions**.
- `spring.profiles.active` cannot be declared inside a document already gated by `spring.config.activate.on-profile` per Config Data rules.

When projects have substantial test configuration, splitting `src/test/resources/application-test.yml` is usually more readable. For a few small values, multi-document YAML is a clean option.

## 20. When @ActiveProfiles Does Not Behave as Expected

### 20.1. Plain JUnit Test Only

~~~java
@ActiveProfiles("test")
class PureUnitTest {

    @Test
    void calculate() {
        var calculator = new Calculator();
        // No Spring ApplicationContext.
    }
}
~~~

`@ActiveProfiles` alone does not create a context. Without Spring TestContext, the annotation has no effect. Keep unit tests independent and pass fakes/mocks via constructors instead of booting Spring just to use a profile.

### 20.2. Spring TestContext Not Enabled

Without `@SpringBootTest`, `@ContextConfiguration`, or a matching test slice/extension, Spring is never asked to load a context. `@ActiveProfiles` does not replace those annotations.

### 20.3. application-test.yml in the Wrong Place

If the file is not on the test classpath or misnamed, Spring Boot will not load it. Check:

~~~text
src/test/resources/application-test.yml
~~~

and confirm the build copies test resources.

### 20.4. Placing @ActiveProfiles on a Method

`@ActiveProfiles` targets classes. Place it on the class or a meta-annotation rather than individual methods.

### 20.5. Mismatched Configuration Prefix

~~~yaml
app:
  notifications:
    enabled: false
~~~

differs from `@ConfigurationProperties(prefix="app.notification")`. Even with the profile active, a wrong key name prevents Binder from populating the expected field.

### 20.6. Property Overridden by Another Source

If `@SpringBootTest(properties="app.message=inline")` or `@DynamicPropertySource` sets the same key, it overrides `application-test.yml`. Do not conclude the profile failed just because a value assertion failed.

### 20.7. Bean Has Multiple Conditions

A bean may carry `@Profile("test")` alongside `@ConditionalOnProperty` or other auto-configuration conditions. A matching profile does not guarantee all other conditions pass.

### 20.8. Profile Inherited from a Superclass

If a superclass has `@ActiveProfiles("integration")` and a subclass has `@ActiveProfiles("test")`, `inheritProfiles=true` causes the context to receive both. To keep only `test`, set `inheritProfiles=false`.

### 20.9. Test Slice Does Not Load the Expected Bean

`@WebMvcTest` does not scan all services/repositories like `@SpringBootTest`. The test profile may be active while the bean simply lies outside the slice's scope.

### 20.10. Context Cache Reuses a Context

Spring TestContext caches contexts with matching merged configurations, where active profiles are a key factor. If a test mutates singletons, static state, or external data without cleanup, tests interfere with each other even with the right profile.

## 21. TestContext Cache and Performance

Booting `@SpringBootTest` takes time. Spring TestContext caching reuses contexts across tests with matching configurations.

Example:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CheckoutTestA {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CheckoutTestB {
}
~~~

If all other configuration elements match, both tests **can** share the same cached ApplicationContext.

Switching to:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "integration"})
class CheckoutTestC {
}
~~~

produces a different profile configuration, creating a distinct cache key and booting a new context.

### Avoid Creating Too Many Slightly Different Profile Variants

If every test class invents its own profile with nearly identical settings, context startups multiply and the suite slows down. Standardize on a base `test` profile, use targeted `@TestPropertySource` overrides when needed, and reserve separate profiles for major bean/Config Data shifts.

### When to Use @DirtiesContext?

`@DirtiesContext` tells the framework to evict the context from cache under defined conditions. Use it only when a test irreversibly dirties context state that normal cleanup cannot restore. Overusing it slows test suites dramatically.

Modifying rows in a test database rarely requires destroying the context; test transactions or data cleanup usually suffice.

## 22. Writing an Integration Test with Real Configuration

Suppose a service uses typed configuration:

~~~java
package com.example.profiledemo.config;

import java.time.Duration;
import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        boolean enabled) {
}
~~~

`src/main/resources/application.yml`:

~~~yaml
app:
  payment:
    endpoint: https://pay.example.org
    timeout: 10s
    enabled: true
~~~

`src/test/resources/application-test.yml`:

~~~yaml
app:
  payment:
    endpoint: http://127.0.0.1:9999
    timeout: 200ms
    enabled: false
~~~

Test:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import com.example.profiledemo.config.PaymentProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {

    @Autowired
    PaymentProperties payment;

    @Autowired
    Environment environment;

    @Test
    void loadsTestPaymentConfiguration() {
        assertThat(environment.getActiveProfiles())
                .contains("test");

        assertThat(payment.enabled()).isFalse();
        assertThat(payment.timeout())
                .isEqualTo(Duration.ofMillis(200));
        assertThat(payment.endpoint())
                .isEqualTo(URI.create("http://127.0.0.1:9999"));
    }
}
~~~

Ensure `PaymentProperties` is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

**Never connect to 127.0.0.1:9999 without a running test server.** This example verifies binding and profile selection only. If a startup bean actively calls a remote API, replace it with a fake adapter or spin up a mock server for the test.

## 23. Verifying a Bean Enabled Only in the Test Profile

Create beans inside a configuration:

~~~java
package com.example.profiledemo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class TestMarkerConfiguration {

    public interface ProfileMarker {
        String name();
    }

    @Bean
    @Profile("test")
    ProfileMarker testProfileMarker() {
        return () -> "test";
    }

    @Bean
    @Profile("!test")
    ProfileMarker defaultProfileMarker() {
        return () -> "default";
    }
}
~~~

Test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ProfileMarkerTest {

    @Autowired
    TestMarkerConfiguration.ProfileMarker marker;

    @Test
    void selectsMarkerForTest() {
        assertThat(marker.name()).isEqualTo("test");
    }
}
~~~

This requires `TestMarkerConfiguration` to be component-scanned by the application. In real apps, profile-scoped adapters might include payment gateways, email senders, or storage clients.

When using `@Profile("!test")` on a default bean, remember it activates in every context lacking `test`, not solely in production.

## 24. Do Not Use Test Profiles in Place of Properly Scoped Mocks

Some tests only need to mock one dependency to test controller or service logic without changing the whole environment configuration.

Creating a global `@Profile("test")` fake bean for every test can cause other integration tests to silently use the fake and miss real connectivity bugs.

Choose appropriately:

- **Unit tests:** construct the class directly with fakes/mocks.
- **Test slices:** supply mocks/fakes scoped to the slice.
- **Integration tests with test profiles:** `@ActiveProfiles("test")` when swapping groups of properties and beans.
- **Integration tests with real infrastructure:** use Testcontainers/embedded services with dynamic properties and intentional profiles.

A test profile is a configuration mechanism; it does not automatically guarantee test isolation or integration depth.

## 25. What Happens Without @ActiveProfiles?

If a test declares only:

~~~java
@SpringBootTest
class ContextLoadsTest {

    @Test
    void contextLoads() {
    }
}
~~~

Spring TestContext does not force profile `test` from annotations. Active profiles may still come from environment, config, or launch arguments; if none are active, Spring uses the default profile per Environment rules.

Never assume `@SpringBootTest` automatically enables `test`. That is a very common false assumption.

If your application defines beans active only under `@Profile("prod")`, a test without that profile will not instantiate them just because it runs on a build machine.

## 26. Running Tests in Maven and Gradle

Maven example:

~~~bash
./mvnw test
~~~

Running a single class with Maven Surefire when supported by project setup:

~~~bash
./mvnw -Dtest=GreetingPropertiesTest test
~~~

Gradle:

~~~bash
./gradlew test
~~~

Or targeting one class:

~~~bash
./gradlew test --tests "com.example.profiledemo.GreetingPropertiesTest"
~~~

On Windows, use the `mvnw.cmd` or `gradlew.bat` wrapper accordingly.

Because `@ActiveProfiles("test")` is declared on the test class, you do not need `-Dspring.profiles.active=test` just to activate the test profile.

To inspect which profiles actually ran, assert `environment.getActiveProfiles()` or check context startup logs.

## 27. Security and Operational Pitfalls

### Test Profiles Do Not Automatically Make Production Connections Safe

Even with `@ActiveProfiles("test")`, a bean without `@Profile` or conditional guards can still start up and call real endpoints inherited from base config. Pair test profiles with:

- Test-only endpoints or local fake servers.
- Dedicated least-privilege credentials.
- Disabled real email, payment, and webhook tasks.
- Restricted CI network egress for sensitive systems.
- Explicit assertions verifying fake adapters are selected.
- Zero real secrets committed inside `src/test/resources`.

### Never Use @ActiveProfiles("prod") Carelessly to Test Production

Activating `prod` can trigger real datasources, queues, schedulers, or external clients. To test production-like configurations, use isolated staging/test environments with fake data and separate access controls.

### Watch Out for @Scheduled and ApplicationRunner

`@SpringBootTest` starts a fairly complete application. `ApplicationRunner`, `CommandLineRunner`, or scheduled jobs can execute during tests if enabled. Gate them with profiles/conditions and test-specific configuration if they cause unintended side effects.

### Avoid Using the "test" Profile as a Security Switch

Whether `test` is active is not authentication or authorization. Never use `@Profile("test")` as a substitute for access control or secret-protection policies.

## 28. Test Organization Pattern for Large Projects

Reference layout:

~~~text
src/test/java/com/example/profiledemo/
├── support/
│   ├── IntegrationTest.java
│   └── CiAwareProfilesResolver.java
├── unit/
│   └── PriceCalculatorTest.java
├── repository/
│   └── CustomerRepositoryTest.java
├── web/
│   └── GreetingControllerTest.java
└── integration/
    ├── PaymentFlowTest.java
    └── NotificationFlowTest.java

src/test/resources/
├── application-test.yml
└── data/
    └── test-customers.json
~~~

Recommended usage:

- Keep unit tests in `unit` without Spring contexts when unnecessary.
- Use `@WebMvcTest`/`@DataJpaTest` for appropriate vertical slices.
- Use `@IntegrationTest` (composed annotation) for tests needing a full context and test profile.
- Use Testcontainers/`@DynamicPropertySource` for integration tests requiring real yet isolated databases or services.
- Keep `application-test.yml` small and stable.
- Apply scenario-specific overrides per test rather than proliferating dozens of near-identical profiles.

Above all, tests must be readable and maintainable: looking at a class should make its profile, context scope, and configuration overrides obvious.

## 29. Quick Comparison Table

| Tool / annotation | Activates profiles? | Supplies properties? | Creates context? |
| --- | --- | --- | --- |
| `@ActiveProfiles("test")` | Yes, via TestContext | Indirectly triggers profile-specific Config Data | Does not create context alone |
| `@Profile("test")` | No | No | No; gates bean registration only |
| `@SpringBootTest` | Does not force `test` profile | Optional via `properties` | Yes, full Spring Boot context as configured |
| `@TestPropertySource` | Does not derive profile from filename | Yes | Does not create context alone |
| `@DynamicPropertySource` | Does not choose profiles | Yes, dynamic values | Does not create context alone |
| `@DataJpaTest` | Does not force `test` profile | Optional via `properties` | Yes, JPA test slice |
| `spring.profiles.active` | Yes during standard app bootstrap | Is a config property | Does not create test context alone |
| `ActiveProfilesResolver` | Yes when referenced by `@ActiveProfiles` | Not directly | Does not create context alone |

If you only need to change one timeout value, `@ActiveProfiles` may be heavier than needed; when swapping an entire set of beans and test config sources, it is the right tool.

## 30. Practice Exercises

### Exercise 1 — Activating a Test Configuration File

Create `src/main/resources/application.yml` with `app.message=default` and `src/test/resources/application-test.yml` with `app.message=from-test`. Write `@SpringBootTest @ActiveProfiles("test")`, inject `Environment`, and assert `from-test`.

### Exercise 2 — Profile-Scoped Beans

Create two implementations of the same interface, one annotated `@Profile("test")` and one `@Profile("!test")`. Write a test verifying the test bean is selected under `@ActiveProfiles("test")`.

### Exercise 3 — Multiple Profiles

Create `application-test.yml` and `application-integration.yml` defining the same key with different values. Annotate `@ActiveProfiles({"test","integration"})` and assert the effective property. Explain why you should not guess precedence from filenames alone.

### Exercise 4 — Inheriting Test Profiles

Create an abstract base class with `@ActiveProfiles("test")`. Write a subclass with `@ActiveProfiles("slow")`. Predict the active profiles with default `inheritProfiles`.

**Answer:** base class profiles are inherited, and the subclass profile is appended.

### Exercise 5 — Disabling Inheritance

On the subclass, set:

~~~java
@ActiveProfiles(profiles = "isolated", inheritProfiles = false)
~~~

Inspect `Environment.getActiveProfiles()` and explain why `test` from the base class is no longer added by annotation inheritance.

### Exercise 6 — TestPropertySource

Create `application-test.yml` with `app.retry.count=2` and a test with `@TestPropertySource(properties="app.retry.count=7")`. Assert the result is 7 when no higher-priority source competes.

### Exercise 7 — DynamicPropertySource

Spin up a local mock server on a random port. Use `@DynamicPropertySource` to supply its URL while also enabling `@ActiveProfiles("test")`. Assert the effective URL, then shut down the server cleanly.

### Exercise 8 — Test Slice

Write `@DataJpaTest @ActiveProfiles("test")` for a repository. Confirm appropriate database dependencies are present. Do not assume the annotation provisions an H2 driver or container automatically.

### Exercise 9 — Profile Resolver

Write an `ActiveProfilesResolver` returning `{"test","ci"}` when `CI=true`, and `{"test"}` otherwise. Verify the profile sets under both conditions and explain the risk of tests diverging between local and CI.

### Exercise 10 — Diagnosing Misconfiguration

A test has `@ActiveProfiles("test")` yet a bean still reads the production endpoint. Check in order:
1. Is `application-test.yml` on the test classpath?
2. Is the property prefix spelled accurately?
3. Is another property source overriding it?
4. Is the bean using `@ConfigurationProperties` or a hardcoded endpoint?
5. Do `@Profile` conditions on the adapter match?
6. Is a different test context being constructed?

### Exercise 11 — Plain Unit Test

A `PriceCalculator` class needs only two constructor arguments and has no Spring dependencies. Write a unit test using `new PriceCalculator(...)` instead of `@SpringBootTest`. Explain why `@ActiveProfiles` is unnecessary.

### Exercise 12 — Avoiding Side Effects

A startup runner sends an email whenever the context boots. Design a fake bean or condition so integration tests do not send real emails when `test` is active. Verify that the test profile selects the fake adapter.

## 31. Summary

`@ActiveProfiles` belongs to the **Spring TestContext Framework** and declares active profiles when the framework loads an `ApplicationContext` for integration tests. In Spring Boot, this typically brings in **`application-test.yml`** or **`application-test.properties`** and activates `@Profile`-gated beans.

Key takeaways:

- Pair with `@SpringBootTest` or an appropriate test slice/ContextConfiguration to actually build a context; `@ActiveProfiles` alone does not.
- Place `@ActiveProfiles("test")` at the class level, not on methods.
- Inspect `Environment.getActiveProfiles()`, not merely the `spring.profiles.active` property string.
- Default `inheritProfiles=true` lets subclasses and nested tests inherit profiles from parent or enclosing classes.
- Use `inheritProfiles=false` when you genuinely need to replace inherited profile lists.
- `ActiveProfilesResolver` allows programmatic profile selection, though tests should stay deterministic.
- `@TestPropertySource`, `@SpringBootTest(properties)`, and `@DynamicPropertySource` override **properties**; they do not replace `@ActiveProfiles`.
- A test profile does not automatically supply database drivers, mock servers, credentials, or guarantee isolation from production.
- For fast suites, choose the right context scope and leverage the TestContext cache intentionally.

## References

- [Spring Framework 6.1 — ActiveProfiles API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/test/context/ActiveProfiles.html)
- [Spring Framework — Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
- [Spring Framework — @ActiveProfiles](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html)
- [Spring Framework — ActiveProfilesResolver API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/test/context/ActiveProfilesResolver.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
