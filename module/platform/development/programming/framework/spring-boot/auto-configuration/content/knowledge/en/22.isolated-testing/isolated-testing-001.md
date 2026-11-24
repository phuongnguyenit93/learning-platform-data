# ApplicationContextRunner and the Benefits of Small Contexts for Auto-Configuration Testing

## 1. Why test auto-configuration in isolation?

A Spring Boot auto-configuration typically registers beans when certain conditions are satisfied: a class is on the classpath, a property is enabled, the application has not provided a replacement bean, or the application is running a suitable web stack.

If you only test by starting the entire application with `@SpringBootTest`, every small change can pull in many unrelated components: component scanning, databases, web servers, messaging, caching, security, and other auto-configurations. Tests become slower, failures are harder to pinpoint, and tests may depend on external environments.

`ApplicationContextRunner` solves this problem by creating **a small, fresh ApplicationContext for each run**, loading only the configurations under test, allowing properties or user beans to be configured, and closing the context after the callback completes.

This tool is particularly well-suited for verifying:

- Whether an auto-configuration creates the default bean when conditions hold.
- Whether the default bean backs off when the user provides a custom bean.
- Whether `@ConditionalOnProperty` reacts properly to present, missing, and `false` values.
- Whether `@ConditionalOnClass` skips an integration when a dependency is not on the classpath.
- Whether `@ConfigurationProperties` binds values and defaults correctly.
- Whether dependent beans are injected properly and the context starts successfully.
- Whether an auto-configuration works independently of other modules.

**The goal is not to test every feature of the application.** We test the contract of a group of configurations and the beans that group is responsible for registering.

## 2. How does ApplicationContextRunner work?

`ApplicationContextRunner` belongs to the `spring-boot-test` module, in package:

```java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
```

A runner describes how to create a context. Each `run(...)` call creates a context from the assembled configuration, executes the test callback, and then closes the context. Therefore, independent runs do not share singleton beans or ApplicationContext state.

Basic flow:

```text
Create ApplicationContextRunner
          |
          v
Add auto-configurations to test
          |
          v
Add user configuration / properties / classloader
          |
          v
runner.run(context -> { assertions })
          |
          v
Create new ApplicationContext
          |
          v
Register bean definitions and evaluate conditions
          |
          v
Instantiate required beans
          |
          v
Assertions in callback
          |
          v
Close context
```

The default runner uses an `AnnotationConfigApplicationContext` suitable for testing non-web configurations. It does not start Tomcat/Jetty and does not automatically scan all application auto-configurations. You only load the configurations you need to test.

### 2.1. Adding auto-configurations to the runner

Common approach:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyAutoConfiguration.class)
                );
```

`AutoConfigurations.of(...)` creates a set of auto-configurations processed by Spring Boot according to auto-configuration ordering. Only the classes passed in belong to this set; the runner does not automatically discover all auto-configuration imports as a full application does.

This keeps tests focused. When testing `CacheAutoConfiguration`, there is no need to accidentally load `DataSourceAutoConfiguration`, `WebMvcAutoConfiguration`, or unrelated configurations.

If a library's auto-configuration has multiple interdependent classes, pass all related auto-configurations or create a deliberate test configuration group. Avoid adding every auto-configuration just to make the context look more like production; doing so diminishes the benefits of small tests.

### 2.2. Registering user configuration

Use `withUserConfiguration(...)` to supply application-provided configuration into the context:

```java
contextRunner
        .withUserConfiguration(UserClientConfiguration.class)
        .run(context -> {
            // Verify user bean and default bean.
        });
```

This is useful for testing `@ConditionalOnMissingBean`, `@Primary`, `@Qualifier`, or user-registered customizers. User configuration is processed by the runner's mechanism alongside the declared auto-configurations.

### 2.3. Passing properties into the context

Use `withPropertyValues(...)`:

```java
contextRunner
        .withPropertyValues(
                "demo.client.enabled=true",
                "demo.client.endpoint=https://api.example.test"
        )
        .run(context -> {
            // Read the bean configured from properties.
        });
```

These values are added to the test context's Environment. You can call `withPropertyValues(...)` multiple times to combine property groups. When testing a missing property, create a run without supplying that key; do not assume that the default value of a `@ConfigurationProperties` object also appears in the Environment.

### 2.4. Replacing the classpath with a custom ClassLoader

Some auto-configurations depend on `@ConditionalOnClass`. To test both present and absent class branches, use `withClassLoader(...)` with `FilteredClassLoader`:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(OptionalClient.class))
        .run(context -> {
            // OptionalClient is absent from this context's classpath.
        });
```

`FilteredClassLoader` belongs to `spring-boot-test`. It lets you simulate a missing library without creating a second project or editing dependency files during test execution.

### 2.5. Other useful options

| Method | Purpose |
| --- | --- |
| `withBean(...)` | Register a test bean by type, name, or supplier |
| `withUserConfiguration(...)` | Add application-provided configuration |
| `withPropertyValues(...)` | Add properties to the Environment |
| `withSystemProperties(...)` | Provide system properties for the run |
| `withClassLoader(...)` | Choose a classloader for the context |
| `withInitializer(...)` | Run an `ApplicationContextInitializer` |
| `withParent(...)` | Attach a parent context when testing hierarchy |
| `withAllowBeanDefinitionOverriding(...)` | Control bean definition overriding policy |
| `withConfiguration(...)` | Add an auto-configuration group |
| `run(...)` | Create the context, run the assertion callback, then close the context |

You do not need to use every method in every test. Add only the inputs that change the condition branch under test.

## 3. Complete example: testing an auto-configuration

Let's build a small integration for `AuditClient`. The auto-configuration creates a default client when:

1. The `AuditClient` class is present.
2. The `demo.audit.enabled` property is `true`, or the key is not declared.
3. The application has not registered a matching `AuditClient` bean.

`AuditProperties` holds `service-name`, and `DefaultAuditClient` receives the value via its constructor. The example makes no network calls, since the goal is to test bean registration and configuration.

### 3.1. Project structure

```text
application-context-runner-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── AuditAutoConfigurationTests.java
```

### 3.2. The pom.xml file

Using Spring Boot `3.5.0` and Java `17`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>application-context-runner-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, Spring Test, and `spring-boot-test` for `ApplicationContextRunner`/`FilteredClassLoader`. No web starter is needed because the sample context is non-web.

### 3.3. The AuditAutoConfigurationTests.java file

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    @ConfigurationProperties(prefix = "demo.audit")
    public static class AuditProperties {

        private String serviceName = "catalog-service";

        public String getServiceName() {
            return serviceName;
        }

        public void setServiceName(String serviceName) {
            this.serviceName = serviceName;
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(AuditProperties.class)
    static class AuditAutoConfiguration {

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnClass(name = "example.AuditClient")
        static class AuditClientConfiguration {

            @Bean
            @ConditionalOnMissingBean(AuditClient.class)
            @ConditionalOnProperty(
                    prefix = "demo.audit",
                    name = "enabled",
                    havingValue = "true",
                    matchIfMissing = true
            )
            AuditClient auditClient(AuditProperties properties) {
                return new DefaultAuditClient(properties.getServiceName());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        AuditClient customAuditClient() {
            return () -> "user-defined-audit";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class)
                    );

    @Test
    void createsDefaultClientWhenConditionsMatch() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AuditProperties.class);
            assertThat(context).hasSingleBean(AuditClient.class);
            assertThat(context).hasBean("auditClient");

            AuditClient client = context.getBean(AuditClient.class);
            assertThat(client.serviceName()).isEqualTo("catalog-service");
        });
    }

    @Test
    void bindsPropertiesIntoTheDefaultClient() {
        runner.withPropertyValues("demo.audit.service-name=orders")
                .run(context -> {
                    AuditClient client = context.getBean(AuditClient.class);

                    assertThat(client.serviceName()).isEqualTo("orders");
                });
    }

    @Test
    void userBeanMakesTheDefaultClientBackOff() {
        runner.withUserConfiguration(UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).hasBean("customAuditClient");
                    assertThat(context).doesNotHaveBean("auditClient");

                    AuditClient client = context.getBean(AuditClient.class);
                    assertThat(client.serviceName())
                            .isEqualTo("user-defined-audit");
                });
    }

    @Test
    void disabledPropertyPreventsDefaultClientCreation() {
        runner.withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                    assertThat(context).hasSingleBean(AuditProperties.class);
                });
    }

    @Test
    void optionalIntegrationIsSkippedWhenItsClassIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                    assertThat(context).hasSingleBean(AuditProperties.class);
                });
    }

    @Test
    void userBeanStillExistsWhenDefaultFeatureIsDisabled() {
        runner.withUserConfiguration(UserAuditConfiguration.class)
                .withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).hasBean("customAuditClient");
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }
}

interface AuditClient {
    String serviceName();
}

record DefaultAuditClient(String serviceName) implements AuditClient {
}
```

### 3.4. Running the tests

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
```

**Expected result:** six JUnit tests pass and Maven finishes with `BUILD SUCCESS` if dependencies download successfully. The tests do not print fixed business stdout; detailed results are in `target/surefire-reports`.

The example is a complete test class, with the auto-configuration placed in test sources to focus on testing techniques. In a real starter, the `AuditAutoConfiguration` class lives in `src/main/java` and is registered in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; the test simply imports it with `AutoConfigurations.of(...)`.

### 3.5. Reading each test as a contract

| Test | Changed condition | Outcome to prove |
| --- | --- | --- |
| `createsDefaultClientWhenConditionsMatch` | No added properties or user bean | Default client is created with defaults |
| `bindsPropertiesIntoTheDefaultClient` | `demo.audit.service-name=orders` | Binder passes the new value into the client |
| `userBeanMakesTheDefaultClientBackOff` | Register user-created `AuditClient` | Default bean does not appear |
| `disabledPropertyPreventsDefaultClientCreation` | `enabled=false` | Default client is not created |
| `optionalIntegrationIsSkippedWhenItsClassIsMissing` | Filter `AuditClient` from classpath | Optional branch is not activated |
| `userBeanStillExistsWhenDefaultFeatureIsDisabled` | User bean and `enabled=false` | Property only disables default bean, does not remove user bean |

A notable detail is the last test. `@ConditionalOnProperty` sits on the factory method creating the default bean; it is not a policy forbidding every `AuditClient` bean in the context. Therefore, the user bean still exists.

## 4. Why do small contexts make better tests?

### 4.1. Speed and clear failure scope

`ApplicationContextRunner` does not scan the whole application and does not start a web server. When an assertion fails, the investigation scope typically includes only:

- Auto-configurations supplied to the runner.
- User configurations added in that run.
- Property values for that run.
- Classpath/classloader for that run.
- Dependencies required by the bean being instantiated.

A test can exercise multiple variants by calling `run(...)` repeatedly, each time with a different builder configuration. The runner is designed as a fluent immutable object: `withPropertyValues(...)` returns a configured runner for subsequent runs without mutating previous context state.

### 4.2. No real database, broker, or HTTP server needed

If the question is only "does the auto-configuration create `AuditClient` when the property is enabled?", the test does not need to connect to a database or send HTTP requests. Dependencies can be replaced with fake beans, suppliers, or mocks in the context.

However, small contexts do not prove real communication works. When a client contains HTTP/JDBC logic, unit tests and integration tests are still needed for timeouts, serialization, network errors, transactions, schemas, or appropriate drivers.

### 4.3. Matrix-based condition testing

Auto-configurations often have multiple conditions. Instead of one large test, separate them into independent cases:

| Class on classpath | Property | User bean | Default outcome |
| --- | --- | --- | --- |
| Present | Missing, `matchIfMissing=true` | Absent | Created |
| Present | `true` | Absent | Created |
| Present | `false` | Absent | Not created |
| Present | `true` | Present | Backs off |
| Absent | Any | Absent | Integration not created |
| Absent | Any | Present | Depends on user bean API and remaining types; optional integration must still be skipped |

You do not need to test every combination if conditions are independent and already covered. However, nested conditions or conditions with interactions should have dedicated tests to prove actual behavior.

## 5. Useful assertions and techniques

### 5.1. Checking bean presence and absence

Commonly used assertions:

```java
assertThat(context).hasSingleBean(AuditClient.class);
assertThat(context).hasBean("auditClient");
assertThat(context).doesNotHaveBean(AuditClient.class);
assertThat(context).doesNotHaveBean("auditClient");
```

Check by type when the contract is a single bean of that type; check by name when the bean name specifically needs verification. Avoid asserting internal bean names that are not published as part of the library's contract.

### 5.2. Checking the bean and actual values

```java
AuditClient client = context.getBean(AuditClient.class);
assertThat(client.serviceName()).isEqualTo("orders");
```

Verifying behavior through an interface makes tests less coupled to implementation details. If a bean is a proxy, asserting against a concrete class or generated class name can make tests brittle.

### 5.3. Checking context startup failure

If a configuration combination is expected to fail, you can assert startup failure:

```java
runner.withPropertyValues("demo.audit.timeout=invalid")
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
```

This is an illustrative snippet; to accurately test validation, configure constraints/dependency validation in the project and assert the appropriate root cause/message. You should not just assert `hasFailed()` if multiple different errors could cause the context to fail.

### 5.4. Checking optional classpath

```java
runner.withClassLoader(new FilteredClassLoader(OptionalCodec.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean(CodecService.class);
        });
```

Place `@ConditionalOnClass` on the configuration class or an appropriate nested configuration so Spring can skip the entire branch referencing optional types. If an optional type appears directly in a method signature of the root configuration, the class may be loaded/introspected before the condition is expected to guard it.

For optional libraries, a conditional nested configuration is usually safer:

```java
@AutoConfiguration
public class CodecAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.codec.OptionalCodec")
    static class OptionalCodecConfiguration {

        @Bean
        CodecService codecService(OptionalCodec codec) {
            return new DefaultCodecService(codec);
        }
    }
}
```

This is an architectural snippet, assuming `OptionalCodec`, `CodecService`, and `DefaultCodecService` belong to the corresponding library. Using `name` on the condition avoids requiring the root configuration to resolve the optional class just to read the annotation; the nested class isolates the method signature that depends on that class.

### 5.5. Checking auto-configuration ordering

If a bean depends on a bean created by another auto-configuration, include the related auto-configurations in `AutoConfigurations.of(...)`. The runner processes auto-configuration order according to Spring Boot's mechanism.

If a test adds only one class and omits the auto-configuration providing a dependency, a `NoSuchBeanDefinitionException` may reflect a missing configuration in the test setup rather than a production bug. Before modifying code, identify which auto-configuration is responsible for the missing bean.

## 6. When to use WebApplicationContextRunner or ReactiveWebApplicationContextRunner?

`ApplicationContextRunner` tests non-web contexts. When an auto-configuration requires Servlet or Reactive web infrastructure, use the matching runner:

| Runner | Context | Suitable for |
| --- | --- | --- |
| `ApplicationContextRunner` | Generic annotation context | JDBC, clients, properties, caches, bean conditions |
| `WebApplicationContextRunner` | Servlet web application context | MVC, Servlet filters, web server factory auto-configuration |
| `ReactiveWebApplicationContextRunner` | Reactive web application context | WebFlux, reactive handlers, codecs |

Servlet example:

```java
new WebApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(MyWebAutoConfiguration.class)
        )
        .run(context -> {
            // Verify MVC or Servlet beans.
        });
```

Reactive example:

```java
new ReactiveWebApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(MyReactiveAutoConfiguration.class)
        )
        .run(context -> {
            // Verify WebFlux beans.
        });
```

These runners also belong to Spring Boot's test utilities. They create the appropriate context type; they do not replace request/response tests via MockMvc or WebTestClient when HTTP behavior must be verified.

## 7. How does ApplicationContextRunner differ from @SpringBootTest and @WebMvcTest?

| Tool | Scope | When to use |
| --- | --- | --- |
| `ApplicationContextRunner` | A small, test-specified group of auto-configurations/beans | Testing conditions, properties, back-off, classpath |
| `WebApplicationContextRunner` | Servlet web configuration group | Testing web auto-configuration at the context level |
| `ReactiveWebApplicationContextRunner` | Reactive web configuration group | Testing WebFlux auto-configuration |
| `@WebMvcTest` | MVC test slice focused on controllers/MVC components | Testing mappings, validation, serialization, MVC advice |
| `@SpringBootTest` | Full application or near-production context | Multi-module integration tests and realistic configurations |

An effective way to organize tests:

1. Use `ApplicationContextRunner` for conditional logic and bean wiring.
2. Use `@WebMvcTest` or WebApplicationContextRunner for MVC-specific behavior.
3. Use `@SpringBootTest` for flows requiring coordination across multiple modules.
4. Use Testcontainers or an integration environment when you need to prove interaction with a real database/broker.

You do not need to replace every `@SpringBootTest` with a runner. Choose the tool based on the question the test needs to answer.

## 8. Limitations to understand

- Runners do not automatically simulate every part of `SpringApplication`. Application-specific listeners, initializers, or environment processing may need to be added explicitly.
- The default runner does not create a Servlet/Reactive web context.
- Classpath filtering simulates a missing class, but does not prove absence of all dependency conflicts or binary incompatibilities.
- Fake/mock beans isolate wiring, but do not verify real communication.
- If an auto-configuration is not added to `AutoConfigurations.of(...)`, the runner will not test it automatically.
- `ApplicationContextRunner` creates a small context; passing tests do not prove the entire production application starts successfully.
- Tests should not rely on unguaranteed bean registration order or proxy class names.
- When conditions interact across multiple auto-configurations, include the complete relevant group to reflect the dependency contract.

## 9. Common mistakes and fixes

1. **Forgetting to add the auto-configuration to the runner.** The test cannot find the bean because the configuration class was never loaded. Use `withConfiguration(AutoConfigurations.of(...))`.
2. **Assuming the runner scans the whole application.** The runner only creates a context from explicitly specified configurations; add `withUserConfiguration` or `withConfiguration` deliberately.
3. **Only testing `property=true`.** Add cases for missing keys, `false`, and invalid values if specified by the contract.
4. **Not testing user bean back-off.** A good starter must allow applications to replace the default bean under published conditions.
5. **Not testing missing optional dependencies on the classpath.** Use `FilteredClassLoader` to verify `@ConditionalOnClass` branches.
6. **Placing optional types on the root configuration.** Isolate references inside a nested configuration annotated with `@ConditionalOnClass`.
7. **Using ApplicationContextRunner for MVC without a web context.** Switch to `WebApplicationContextRunner` or an MVC test slice.
8. **Only asserting the context has no errors.** Verify that beans actually exist, property values are bound, and key behaviors work.
9. **Asserting on proxy class names.** Verify interfaces and behavior rather than framework-generated implementation classes.
10. **Testing too many unrelated auto-configurations.** Add only the required group; broader tests make root causes harder to find.
11. **Sharing context or mutable state across tests.** Each `run` creates a separate context; avoid static mutable state outside the context.
12. **Mocking every dependency and concluding real integration works.** Add integration tests with real databases/brokers/clients where needed.
13. **Not checking startup failure for the right cause.** Assert the specific root cause or message when testing validation/condition failures.
14. **Forgetting the test dependency.** Ensure the module has `spring-boot-starter-test` or the corresponding dependency in test scope.
15. **Confusing the test module classpath with the consumer classpath.** Tests in an autoconfigure module might always see optional dependencies via test dependencies; add a consumer sample without that library.

## 10. Auto-configuration testing checklist

- [ ] Selected the right runner: generic, Servlet, or Reactive.
- [ ] Added the right auto-configuration(s) via `AutoConfigurations.of(...)`.
- [ ] Included default test when properties are absent.
- [ ] Included tests for property override and disable.
- [ ] Included test for user bean causing auto-configuration to back off.
- [ ] Included test for missing optional class via `FilteredClassLoader` when class conditions exist.
- [ ] Included assertions for beans by appropriate type/name and actual values.
- [ ] Included startup failure test for invalid configuration if the library supports validation.
- [ ] Test context requires no real database/network when only checking bean wiring.
- [ ] Separate integration test exists for real communication when needed.
- [ ] Verified the runner does not omit auto-configurations providing dependencies.
- [ ] Tests do not rely on proxy classes, incidental ordering, or implementation details.

## 11. Self-check questions

**Question 1.** What is `ApplicationContextRunner` best suited to test?  
**Answer:** Independent auto-configuration branches such as class conditions, property conditions, bean back-off, properties binding, and dependency injection in a small context.

**Question 2.** Does the runner automatically load all auto-configurations in an application?  
**Answer:** No. Tests must specify the configuration group, typically via `AutoConfigurations.of(...)`.

**Question 3.** Which method do you use to test that auto-configuration backs off when a user provides a bean?  
**Answer:** `withUserConfiguration(...)` or `withBean(...)`, then assert that the default bean does not appear and the user bean exists.

**Question 4.** What do you use to test a `@ConditionalOnClass` branch when a library is not on the classpath?  
**Answer:** `withClassLoader(new FilteredClassLoader(OptionalType.class))`.

**Question 5.** Does each `run(...)` call reuse the previous ApplicationContext?  
**Answer:** No. The runner creates a fresh context per run and closes it after the callback, keeping scenarios independent.

**Question 6.** Should `ApplicationContextRunner` be used to test controller mappings and HTTP serialization?  
**Answer:** Use a web runner or `@WebMvcTest`/MockMvc for MVC behavior; ApplicationContextRunner is not a web context by default.

**Question 7.** Does a passing runner test prove a real database connection succeeds?  
**Answer:** Not if the test only uses fake beans or never opens a connection. An integration test with an appropriate database is needed.

**Question 8.** Why test both a missing property and `false`?  
**Answer:** `matchIfMissing`, default values, and `havingValue` determine different behaviors; testing only `true` does not prove the other two branches.

## Official reference documentation

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, testing with `ApplicationContextRunner` section: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 API — `WebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html
- Spring Boot 3.5 API — `ReactiveWebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html
- Spring Boot 3.5 API — `FilteredClassLoader`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Takeaway:** `ApplicationContextRunner` enables testing an auto-configuration in a small, isolated, reproducible context. Load only the necessary configurations, vary properties/user beans/classpath per scenario, and verify actual beans and behavior. Use web runners or integration tests when questions go beyond bean wiring.
