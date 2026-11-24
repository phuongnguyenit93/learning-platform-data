# Relationship Between Test Slices, Imported Auto-Configurations, and Full Application Tests

## 1. Why can the same bean appear in one test and vanish in another?

Spring Boot has multiple ways to build an ApplicationContext for testing. Two common approaches are:

- **Test slices** such as **@WebMvcTest**, **@DataJpaTest**, **@JsonTest**, **@RestClientTest**: load only a slice of the application suited to the layer under test.
- **Full application tests** with **@SpringBootTest**: build the context from the main application configuration and apply the corresponding auto-configuration system.

A common point of confusion is that a test slice **is not a full context with a few beans turned off**. A slice has its own component-selection mechanism and its own list of imported auto-configurations. Consequently, an auto-configuration can work in the real application yet not be loaded in @WebMvcTest, or a @Component bean can exist in the full context yet not be picked up by the slice's component scan.

When debugging a "bean exists in the app but the test cannot find it" issue, answer:

1. Which type of context is the test using?
2. Which components does that slice scan?
3. Which auto-configurations are imported by default?
4. Is the application/library's auto-configuration on that list?
5. If extra configuration is needed, should we use @Import, @ImportAutoConfiguration, @EnableConfigurationProperties, or switch to @SpringBootTest?

This article uses **Spring Boot 3.5.16, Java 17+, and JUnit 5**. Specific auto-configuration lists can change across Boot versions; when investigating a real project, always consult the appendix for the exact version in use.

## 2. Three-layer model: test slice, imported auto-configuration, and full context

The relationship can be visualized as follows:

~~~text
                         Spring Boot app
                               |
                    @SpringBootApplication
                               |
                    @EnableAutoConfiguration
                               |
                 AutoConfiguration.imports
                               |
                 Candidate auto-configurations
                               |
                 Conditions + classpath + beans
                               |
                     Full ApplicationContext
                               |
             @SpringBootTest (full application)
                               |
          -------------------------------------------
          |                                         |
     Test slice                              Full app test
          |                                         |
   @WebMvcTest / @DataJpaTest                 @SpringBootTest
          |                                         |
   Restricted component scan                Main scan/config
          |                                         |
   Dedicated auto-config list               Eligible auto-configs
          |                                         |
   Imported auto-config subset              Multiple real bean layers
          |
   Can be extended via
   @ImportAutoConfiguration
~~~

Three concepts to distinguish:

| Concept | Meaning |
| --- | --- |
| **Test slice** | A way to build a context restricted to one part of the application, such as web MVC or JPA |
| **Imported auto-configuration** | The auto-configuration classes that the slice explicitly brings into the context |
| **Full application test** | A context built from main configuration, allowing application components and auto-configurations to participate according to conditions |

Spring Boot provides a group of test annotations in the spring-boot-test-autoconfigure module. Each slice combines an @...Test annotation with one or more @AutoConfigure... annotations to load required configuration. Each slice restricts component scanning and loads only a narrow set of auto-configurations. See [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

## 3. What does a test slice do and not do?

### 3.1. A test slice focuses on one layer

Some examples:

| Annotation | Focused area under test | Typically auto-configured infrastructure |
| --- | --- | --- |
| @WebMvcTest | Controllers, MVC mappings, web-related validation/converters/filters | Spring MVC, message converters, MockMvc, certain Security configs if present |
| @WebFluxTest | WebFlux controllers and reactive web layer | WebFlux, codecs, WebTestClient |
| @DataJpaTest | Entities, repositories, JPA mappings, and queries | DataSource, Hibernate/JPA, transactions, repository support |
| @JdbcTest | JDBC components/repositories | DataSource, JdbcTemplate, transactions, and test database support |
| @JsonTest | JSON serialization/deserialization | Jackson/Gson/Jsonb and JSON testers |
| @RestClientTest | Code calling external REST services | RestClient/RestTemplate builders, message converters, and mock server |

Official auto-configuration lists are documented in the appendix [Spring Boot 3.5 — Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html). For instance, @WebMvcTest includes WebMvcAutoConfiguration, HttpMessageConvertersAutoConfiguration, MockMvcAutoConfiguration, and related configs; @DataJpaTest includes DataSourceAutoConfiguration, HibernateJpaAutoConfiguration, repository, transaction, and test database support.

Do not treat the table above as an exhaustive list. Dependencies on the classpath, test attributes, and bean conditions can make the actual loaded set differ.

### 3.2. Component scan is restricted

For example, @WebMvcTest scans only MVC-related component types such as:
- @Controller and @ControllerAdvice;
- @JsonComponent;
- Converter and GenericConverter;
- Filter, HandlerInterceptor;
- WebMvcConfigurer, WebMvcRegistrations;
- HandlerMethodArgumentResolver.

Regular @Component and @ConfigurationProperties beans are not automatically scanned in this slice. If a properties bean is needed, use @EnableConfigurationProperties; if a helper component is needed, import its configuration explicitly or supply a mock. See [Spring Boot 3.5 — Auto-configured Spring MVC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

@DataJpaTest also does not scan regular @Component and @ConfigurationProperties; it focuses on entities and Spring Data JPA repositories. It typically uses an embedded database if a matching dependency is on the classpath and by default runs each test in a transaction that rolls back afterward.

### 3.3. Why should multiple slice annotations not be combined on one test?

Combining multiple @...Test slice annotations on the same test class is not supported, for example:

~~~java
// Do not use this approach to try combining two slices.
@WebMvcTest
@DataJpaTest
class InvalidCombinedSliceTests {
}
~~~

If you need some capabilities of another slice, choose one primary slice and add the appropriate @AutoConfigure... annotations. If the goal is to test the full controller → service → repository path, @SpringBootTest is usually clearer.

## 4. Where does a slice's imported auto-configuration set come from?

A slice does not simply scan every AutoConfiguration.imports file and enable every auto-configuration. Slice annotations carry their own metadata specifying the group of auto-configurations they need.

Selection rationale examples:

- @WebMvcTest needs MVC, message conversion, MockMvc, and relevant web integrations.
- @DataJpaTest needs DataSource, JPA provider, repositories, transactions, and test database.
- @JsonTest needs JSON mappers and JSON test helpers.
- @RestClientTest needs client builders, message converters, and MockRestServiceServer.

Auto-configurations must still pass their own conditions: classpath, properties, existing beans, ApplicationContext type, and other conditions. Having a class on the imported list **does not guarantee its beans will be created**.

This can be illustrated as:

~~~text
Slice imports auto-configuration class
                |
                v
Class-level conditions match?
                |
                v
Nested configuration / @Bean conditions match?
                |
                v
No user bean makes it back off?
                |
                v
Bean definition is registered
                |
                v
Bean instance is created when required
~~~

This is why we must distinguish:
- **Imported:** the configuration is fed into processing.
- **Condition matched:** the configuration or bean method's conditions passed.
- **Bean definition registered:** Spring holds metadata to create the bean.
- **Instance created:** the actual object is instantiated when lifecycle requires it.

Looking only at annotations on the test class is not enough to conclude the final bean definitely exists.

## 5. @ImportAutoConfiguration: adding auto-configurations to a slice

When a slice lacks an auto-configuration that a test needs, you can add it specifically for that test using @ImportAutoConfiguration.

Example:

~~~java
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.autoconfigure.integration.IntegrationAutoConfiguration;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class JdbcIntegrationTests {
}
~~~

@ImportAutoConfiguration brings the specified auto-configurations into the test context and lets Spring Boot process them via auto-configuration mechanics.

**Do not use regular @Import to import an auto-configuration class.** Spring Boot processes auto-configurations according to dedicated ordering and rules; @ImportAutoConfiguration is the purpose-built annotation. The official documentation illustrates this in [Additional Auto-configuration and Slicing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

### 5.1. When to use @ImportAutoConfiguration?

Use it when:
- A slice needs one specific auto-configuration that is not imported by default;
- You want to test interaction between a slice and a library's auto-configuration;
- You want to run a test with an explicit set of auto-configurations;
- You want to keep test scope small instead of switching the whole test to a full context.

### 5.2. When to use @Import?

@Import fits regular configurations owned by the application, such as:
- A @Configuration class providing test fixtures;
- A specific converter, mapper, or helper bean;
- A security configuration needed inside a controller slice;
- A @TestConfiguration supplementing a test.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class GreetingTestSupportConfiguration {

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}

@WebMvcTest(GreetingController.class)
@Import(GreetingTestSupportConfiguration.class)
class GreetingControllerTests {
}
~~~

If a @Configuration class contains many beans spanning different domains, split it into smaller configurations. A slice should import only what it needs, avoiding pulling a DataSource or external client into a test that only needs MVC.

### 5.3. Distinguishing configuration import mechanisms

| Mechanism | Used for | Example |
| --- | --- | --- |
| @Import | Regular config/selector/bean configuration | @Import(MyTestConfiguration.class) |
| @ImportAutoConfiguration | Spring Boot auto-configuration | @ImportAutoConfiguration(MyLibraryAutoConfiguration.class) |
| @EnableConfigurationProperties | Registering one or more properties types | @EnableConfigurationProperties(MyProperties.class) |
| @ComponentScan | Scanning components by package/filter | Use intentionally; avoid breaking slice boundaries |
| @SpringBootTest | Bootstrapping the app using main configuration | @SpringBootTest |

## 6. Adding an auto-configuration to every test using a slice

If many @JdbcTest tests all need the same auto-configuration, there is no need to repeat @ImportAutoConfiguration on every class.

You can create a file in test resources:

~~~text
src/test/resources/META-INF/spring/
└── org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports
~~~

Content:

~~~text
com.example.IntegrationAutoConfiguration
~~~

Listed auto-configurations are added to every test using @JdbcTest on that classpath.

Key notes:
- The file must be placed under META-INF/spring.
- The file name must match the slice annotation exactly.
- Lines starting with # can be used for comments.
- This mechanism applies to slices or @AutoConfigure... annotations meta-annotated with @ImportAutoConfiguration.
- If only a single test needs the configuration, @ImportAutoConfiguration on the test class is usually clearer.

This is a suite-wide extension mechanism, so use it only when all tests for that slice genuinely need the same configuration.

## 7. @SpringBootTest: full application testing

@SpringBootTest creates an ApplicationContext through SpringApplication. If no main configuration is specified, Spring Boot searches upward from the test's package until it finds @SpringBootApplication or @SpringBootConfiguration.

When running a full context:
- The application's component scan is applied;
- Auto-configurations registered by @EnableAutoConfiguration can participate;
- Spring Boot property sources are installed in the context;
- Conditions continue deciding which beans are created;
- User-defined beans can cause auto-configurations to back off.

By default, @SpringBootTest does not start a real server. The webEnvironment attribute controls the environment:

| Value | Behavior |
| --- | --- |
| MOCK (default) | Web ApplicationContext with a mock web environment; no embedded server |
| RANDOM_PORT | Starts a real web server on a random port |
| DEFINED_PORT | Starts a real web server on the configured or default port |
| NONE | ApplicationContext with no web environment |

If you want to use MockMvc in a full context, combine @SpringBootTest with @AutoConfigureMockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class FullApplicationMvcTests {

    @Autowired
    MockMvc mockMvc;

    // Tests controller within the full application context.
}
~~~

This is a **full application test with MockMvc**, not a @WebMvcTest slice. It is useful when you need to verify a controller working together with real services, repositories, security, serializers, and application configuration.

When you need to test a real HTTP server, use webEnvironment = RANDOM_PORT or DEFINED_PORT and send requests through an appropriate HTTP client. Note that the server and test client run on different threads; a test transaction does not automatically roll back changes committed on the server thread.

See [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

## 8. Complete example: a custom auto-configuration used in slices and full tests

The example creates a greeting service. Auto-configuration provides a default GreetingService if the property is enabled and the application has not provided its own bean. A controller uses this service.

### 8.1. Project structure

~~~text
greeting-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── GreetingController.java
    │   │   ├── GreetingResponse.java
    │   │   ├── GreetingService.java
    │   │   ├── DefaultGreetingService.java
    │   │   └── autoconfigure/GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/demo/
            ├── GreetingAutoConfigurationTests.java
            ├── GreetingControllerSliceTests.java
            └── GreetingApplicationIntegrationTests.java
~~~

### 8.2. Maven dependencies

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>greeting-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. Service API and default implementation

File GreetingService.java:

~~~java
package com.example.demo;

public interface GreetingService {

    String greet(String name);
}
~~~

File DefaultGreetingService.java:

~~~java
package com.example.demo;

public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

The implementation does not need @Component. Auto-configuration registers the default bean via @Bean.

### 8.4. Auto-configuration

File autoconfigure/GreetingAutoConfiguration.java:

~~~java
package com.example.demo.autoconfigure;

import com.example.demo.DefaultGreetingService;
import com.example.demo.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Meaning:
- @AutoConfiguration marks the class as an auto-configuration.
- @ConditionalOnProperty enables the configuration only when demo.greeting.enabled=true; if the property is not declared, it still enables because matchIfMissing=true.
- @ConditionalOnMissingBean(GreetingService.class) lets the application supply a different service.
- The default bean is created only when conditions match.

### 8.5. Registering auto-configuration for Boot applications

Create the file:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Content:

~~~text
com.example.demo.autoconfigure.GreetingAutoConfiguration
~~~

This is how auto-configuration is discovered when an application uses @EnableAutoConfiguration or @SpringBootApplication. Full application tests will load this class through auto-configuration discovery if the resource is packaged on the classpath.

### 8.6. Controller and response

File GreetingResponse.java:

~~~java
package com.example.demo;

public record GreetingResponse(String message) {
}
~~~

File GreetingController.java:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/greeting")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    public GreetingResponse greet(@PathVariable String name) {
        return new GreetingResponse(this.greetingService.greet(name));
    }
}
~~~

File DemoApplication.java:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.7. Standalone auto-configuration test with ApplicationContextRunner

Before testing slices or the full app, test auto-configuration logic in isolation. This verifies properties, conditions, and user overrides without needing MVC or a database.

File GreetingAutoConfigurationTests.java:

~~~java
package com.example.demo;

import com.example.demo.autoconfigure.GreetingAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void createsDefaultServiceWhenEnabledOrPropertyMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("Ada"))
                    .isEqualTo("Hello, Ada");
        });
    }

    @Test
    void doesNotCreateServiceWhenDisabled() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void userServiceMakesDefaultBeanBackOff() {
        runner.withUserConfiguration(CustomGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class).greet("Ada"))
                            .isEqualTo("Custom, Ada");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService greetingService() {
            return name -> "Custom, " + name;
        }
    }
}
~~~

Points to verify:
- Property undeclared: the default service is still created.
- Property false: the service is not created.
- User configuration provides its own service: the default bean backs off and the user's bean is used.

ApplicationContextRunner is suited for testing a single auto-configuration independently, not as a full application test. If you need to test a missing optional dependency, use FilteredClassLoader to simulate a missing library on the classpath.

### 8.8. Slice test: @WebMvcTest and @ImportAutoConfiguration

File GreetingControllerSliceTests.java:

~~~java
package com.example.demo;

import com.example.demo.autoconfigure.GreetingAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
@ImportAutoConfiguration(GreetingAutoConfiguration.class)
class GreetingControllerSliceTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void controllerUsesDefaultServiceImportedForThisSlice() throws Exception {
        mockMvc.perform(get("/greeting/{name}", "Ada"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello, Ada"));
    }
}
~~~

@WebMvcTest(GreetingController.class) restricts component scanning to the controller and matching MVC components. GreetingService is not an MVC component, so component scanning does not find it. @ImportAutoConfiguration brings GreetingAutoConfiguration into the slice to supply the default service.

If @ImportAutoConfiguration is removed, the test can fail when constructing the controller because GreetingService is not found. This is a classic example of an application auto-configuration being present in the full context yet absent from the slice's imported set.

This test does not start an embedded HTTP server. MockMvc executes the request through Spring MVC infrastructure inside a mock web context.

### 8.9. Full application test: @SpringBootTest

File GreetingApplicationIntegrationTests.java:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class GreetingApplicationIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void applicationDiscoversAutoConfigurationAndServesRequest()
            throws Exception {

        assertThat(applicationContext)
                .hasSingleBean(GreetingService.class);

        mockMvc.perform(get("/greeting/{name}", "Ada"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Ada"));
    }
}
~~~

In this test:
- @SpringBootTest locates DemoApplication and builds the full application context.
- @SpringBootApplication enables auto-configuration.
- AutoConfiguration.imports lets Spring Boot discover GreetingAutoConfiguration.
- The demo.greeting.enabled condition and @ConditionalOnMissingBean still determine the final service.
- @AutoConfigureMockMvc adds MockMvc to call endpoints without starting a real server.

Key difference: a slice test needs to import custom auto-configuration explicitly if the slice does not include it; a full application test automatically loads auto-configurations registered in AutoConfiguration.imports.

### 8.10. Running the tests

Run all:

~~~bash
mvn test
~~~

Run each group individually:

~~~bash
mvn test -Dtest=GreetingAutoConfigurationTests
mvn test -Dtest=GreetingControllerSliceTests
mvn test -Dtest=GreetingApplicationIntegrationTests
~~~

Expected result:
- Auto-configuration tests: 3 tests PASS.
- Controller slice: 1 test PASS.
- Full application test: 1 test PASS.

These are the test method counts written in the example; exact Maven/Surefire output logs vary by version. The tests use isolated contexts suited to each goal and call no external services.

## 9. Comparing the three testing approaches on the same auto-configuration

| Aspect | ApplicationContextRunner | Test slice | @SpringBootTest |
| --- | --- | --- | --- |
| Goal | Testing auto-configuration logic | Testing one application layer with required infrastructure | Full-application integration testing |
| Component scan scope | Does not auto-scan app; test declares explicit configs | Restricted to the slice | Follows main application configuration |
| Auto-configuration | Only classes the test passes to the runner | Slice's dedicated imported set + additions | Candidates enabled by app whose conditions match |
| Properties | Easy to add via withPropertyValues | Uses test annotation properties or test property sources | Uses @SpringBootTest(properties=...), profiles, config files |
| User bean override | Easy to create via withUserConfiguration | Uses @Import, @MockitoBean, or test configuration | Can use real beans or intentional mocks |
| HTTP server | Not the goal | Mock web infrastructure if it is a web slice | MOCK by default; RANDOM_PORT/DEFINED_PORT for a real server |
| Speed | Usually fastest | Medium | Usually heaviest |

A balanced strategy is usually:
1. Unit tests for plain Java logic.
2. ApplicationContextRunner for the auto-configuration contract.
3. Test slices for each web/data/client layer.
4. A small set of @SpringBootTest tests for critical integration flows.

There is no need to move every test to a full context. Full contexts are slower and can make test failures harder to pinpoint.

## 10. When to add auto-configuration vs. when to mock a bean?

Suppose a controller needs GreetingService. There are two different test goals:

**Testing the controller independently of the service:**

~~~java
@WebMvcTest(GreetingController.class)
class GreetingControllerWithMockTests {

    @MockitoBean
    GreetingService greetingService;
}
~~~

Mocking the service tests mappings, status codes, JSON, and request handling without testing auto-configuration.

**Testing the controller with the default service:**

~~~java
@WebMvcTest(GreetingController.class)
@ImportAutoConfiguration(GreetingAutoConfiguration.class)
class GreetingControllerWithDefaultServiceTests {
}
~~~

This tests the interaction between the controller and the auto-configured service.

**Testing the full application:**

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class GreetingFullApplicationTests {
}
~~~

This tests the controller together with services, component scanning, and the application's other auto-configurations.

Choose based on the question the test must answer. If the controller test only needs simulated service results, mocking keeps the test focused. If the goal is to prove auto-configuration supplies the right bean for the controller, import the real auto-configuration.

## 11. Organizing configurations so slices do not pull unnecessary beans

A large @Configuration class might declare SecurityFilterChain, DataSource, clients, and MVC configurers together. Importing that entire class into @WebMvcTest can trigger creation of all its beans, including a DataSource not needed for web tests.

Split by domain instead:

~~~text
config/
├── WebSecurityConfiguration.java
├── PersistenceConfiguration.java
├── ExternalClientConfiguration.java
└── JsonConfiguration.java
~~~

Then each slice imports only the relevant part:

~~~java
@WebMvcTest(GreetingController.class)
@Import(WebSecurityConfiguration.class)
class GreetingSecuritySliceTests {
}
~~~

Or:

~~~java
@DataJpaTest
@Import(PersistenceTestConfiguration.class)
class RepositorySliceTests {
}
~~~

For auto-configurations, use @ImportAutoConfiguration. For regular configurations, use @Import. If a configuration is strictly for tests, use a nested @TestConfiguration; that annotation supplements the test's main configuration.

Spring Boot documentation recommends against placing domain-specific configuration directly on the @SpringBootApplication class, since that class is often used as the configuration source for tests. Moving domain-specific configuration into separate classes lets slices enable only what is needed.

## 12. Excluding an auto-configuration from a slice

Sometimes a slice imports an auto-configuration by default that is unsuitable for a test. It can be excluded.

Example:

~~~java
@WebMvcTest(
        controllers = GreetingController.class,
        excludeAutoConfiguration = SomeUnwantedAutoConfiguration.class)
class GreetingControllerWithoutExtraConfigurationTests {
}
~~~

Or use the exclude attribute of @ImportAutoConfiguration when appropriate:

~~~java
@ImportAutoConfiguration(
        exclude = SomeUnwantedAutoConfiguration.class)
~~~

Use exclusions when:
- The slice does not need a specific integration;
- A test dependency on the classpath causes an auto-configuration to match when the test does not want it enabled;
- You want to isolate a layer from external infrastructure.

Before excluding, inspect the condition report or the imported auto-configuration list for your exact Boot version. Do not exclude a configuration merely because its name looks unrelated; it may provide an infrastructure bean the slice needs.

## 13. Diagnosing when a bean exists in the full app but not in a slice

Follow these steps in order:

1. **Identify the test annotation:** @WebMvcTest, @DataJpaTest, @RestClientTest, or @SpringBootTest.
2. **Check which auto-configurations the slice imports:** look up the appendix for the exact Boot version.
3. **Check component scan filters:** is the missing bean a @Component, @ConfigurationProperties, @Bean, or auto-configured bean?
4. **If it is a component:** check whether that component type belongs to the slice's scan; consider @Import, @MockitoBean, or @EnableConfigurationProperties.
5. **If it is a regular configuration:** import the needed configuration class with @Import; prefer splitting large configs to avoid pulling extra beans.
6. **If it is an auto-configuration:** add it with @ImportAutoConfiguration, or register it in the slice imports file if all tests of that slice need it.
7. **Check conditions:** classpath, properties, existing beans, context type, @ConditionalOnMissingBean, and auto-configuration ordering.
8. **If multiple layers are needed at once:** switch to @SpringBootTest instead of trying to combine multiple slices.
9. **Create a dedicated test for the auto-configuration:** use ApplicationContextRunner to verify conditions and bean registration independently.
10. **Re-run tests:** verify the context issue is resolved without pulling unnecessary dependencies.

### 13.1. Condition Evaluation Report

You can run the test/application with appropriate debug logging or inspect ConditionEvaluationReport to see which auto-configurations matched or backed off. This helps when a class was imported yet the bean is still absent.

Distinguish between:
- Not imported into the slice;
- Imported, yet class-level conditions did not match;
- Class-level matched, yet method-level conditions did not match;
- Default bean backed off due to a user bean;
- Bean definition existed, yet instance creation failed.

Each case has a different root cause and fix.

## 14. Common mistakes

| Error | Why it happens | Fix |
| --- | --- | --- |
| @Component bean exists in app yet is absent in @WebMvcTest | Slice does not scan regular components | Use @MockitoBean or @Import if a real bean is needed |
| @ConfigurationProperties is not injected in a slice | Slice does not scan regular properties beans | Use @EnableConfigurationProperties |
| Auto-configuration works in full app yet is absent in slice | Slice imports only a restricted subset of auto-configurations | Add it via @ImportAutoConfiguration |
| Using @Import to import an auto-configuration | Bypasses Boot's specialized processing | Use @ImportAutoConfiguration |
| Adding both @WebMvcTest and @DataJpaTest to one class | Multiple slice annotations cannot be combined | Choose one slice or use @SpringBootTest |
| Importing a large config makes a slice unexpectedly start a DB | Config contains beans outside the slice | Split config by domain and import only what is needed |
| Full test cannot find custom auto-configuration | Not registered in AutoConfiguration.imports or not imported | Check imports resource and package/class name |
| Auto-configuration is imported yet bean is still missing | Conditions do not match or it backed off | Inspect condition messages and user beans |
| @SpringBootTest runs slower than a slice | Full context loads many components/auto-configurations | Use slices for layer tests; keep few full integration tests |
| Assuming server.port=0 is a mock web test | Port 0 still starts a real server | Use WebEnvironment.MOCK for MockMvc without a server |
| @ImportAutoConfiguration intended for one test affects many tests | Config was registered globally in a slice imports file | Use the annotation on the single test class if only one test needs it |
| @TestConfiguration is not loaded | Not imported or declared in the wrong scope | Use a nested test config or explicit @Import |

## 15. Test selection matrix

| Goal | Recommended approach | Reason |
| --- | --- | --- |
| Testing auto-configuration @ConditionalOnProperty | ApplicationContextRunner | Easy property control and bean assertions |
| Testing @ConditionalOnMissingBean | ApplicationContextRunner + user config | Verifies default back-off when user bean exists |
| Testing controller mappings and JSON | @WebMvcTest | Loads only MVC layer and MockMvc |
| Controller needs a default bean from custom auto-config | @WebMvcTest + @ImportAutoConfiguration | Keeps slice while adding just the needed auto-config |
| Testing repositories and JPA mappings | @DataJpaTest | Includes entities/repositories, transactions, and test DB |
| Testing REST client calling external services | @RestClientTest | Provides builders and mock server |
| Testing serializers/deserializers | @JsonTest | Focuses on JSON mappers/testers |
| Testing controller → service → repository | @SpringBootTest | Requires multiple layers coexisting |
| Testing real server, port, HTTP stack | @SpringBootTest(RANDOM_PORT) | Starts embedded server |
| Testing a custom auto-config in a full app | @SpringBootTest | Confirms discovery during application bootstrap |
| Testing multiple auto-configs cooperating without full app | ApplicationContextRunner with multiple classes | Explicit control over config list and conditions |

## 16. Self-check questions

**Question 1.** Why can an auto-configuration work in @SpringBootTest yet be absent in @WebMvcTest?

**Answer:** @SpringBootTest builds the context from main configuration and applies the application's auto-configurations. @WebMvcTest imports only a limited set of MVC-related auto-configurations. If a custom auto-configuration is not in that set, it must be added with @ImportAutoConfiguration.

**Question 2.** Which annotation adds an auto-configuration to a slice?

**Answer:** @ImportAutoConfiguration.

**Question 3.** When is @Import used?

**Answer:** When importing a regular configuration, test support configuration, or specific component; do not use @Import instead of @ImportAutoConfiguration for auto-configurations.

**Question 4.** Does @WebMvcTest scan all @Component and @ConfigurationProperties classes?

**Answer:** No. It restricts scanning to MVC component types. Use @EnableConfigurationProperties, @Import, or appropriate mock collaborators.

**Question 5.** Can @WebMvcTest and @DataJpaTest be combined on the same test class?

**Answer:** No. Spring Boot does not support combining multiple slice annotations like that. Pick one primary slice, add @AutoConfigure... annotations if needed, or use @SpringBootTest.

**Question 6.** Does @SpringBootTest start a real embedded server by default?

**Answer:** No. The default is WebEnvironment.MOCK. Use RANDOM_PORT or DEFINED_PORT to start a real server.

**Question 7.** What should be used to test a custom auto-configuration before bringing it into the full app?

**Answer:** ApplicationContextRunner to test properties, conditions, default beans, and user bean overrides independently.

## 17. Official References

- Spring Boot 3.5 — Testing Spring Boot Applications, test slices, full context, additional auto-configuration, and @ImportAutoConfiguration: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Test Slices appendix, auto-configuration list imported by each slice: https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- Spring Boot 3.5 — Testing how-to, structuring configuration for slice tests: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Boot 3.5 API — ImportAutoConfiguration: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html
- Spring Boot 3.5 API — SpringBootTest: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html
- Spring Boot 3.5 API — WebMvcTest: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, testing with ApplicationContextRunner: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
