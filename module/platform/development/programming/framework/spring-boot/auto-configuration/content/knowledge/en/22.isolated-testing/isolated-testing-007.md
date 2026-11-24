# Verifying Configured Values Are Bound to Default Beans

## 1. Goal: verifying the final outcome in the bean

In Spring Boot, seeing a property in a configuration file or seeing a `@ConfigurationProperties` object receive a value is not yet enough to conclude the default bean works properly. You need to verify the entire path:

1. The value is present in `Environment` from the intended configuration source.
2. Spring Binder converts the value to the right type and binds it to the properties object.
3. Auto-configuration accepts the properties object or binds directly to the bean.
4. The default bean is created with the expected effective values.
5. If the application supplies a replacement bean, auto-configuration backs off as designed.

For example, `spring.datasource.url` may bind properly to `DataSourceProperties`, yet the final `DataSource` bean could still be wrong if another configuration replaces it or pool-specific properties fail to bind as expected. Therefore, tests should inspect **the actual bean the application will inject**, not just the intermediate configuration object.

This article uses **Spring Boot 3.5.x, Java 17+, and JUnit 5**. The main example tests `DataSourceAutoConfiguration` with `HikariDataSource`, running against H2 in-memory to avoid external database dependencies.

## 2. Three layers to verify

| Layer | Question | How to test |
| --- | --- | --- |
| `Environment` | Which property holds the effective value? | `Environment.getProperty(...)` |
| Properties bean | Did the Binder convert values to the right Java fields/types? | Retrieve the `@ConfigurationProperties` bean and assert each value |
| Default bean | Did the factory method use those values to build the right bean? | Retrieve the bean by its actual type, assert getters or public behavior |

Example:

- `spring.datasource.url` and `spring.datasource.username` belong to general DataSource configuration.
- `spring.datasource.hikari.maximum-pool-size` belongs to Hikari-specific configuration.
- `DataSourceProperties` checks general JDBC configuration.
- `HikariDataSource` checks the values that actually reached the default pool.

**Do not stop at the properties bean.** If a test only confirms `DataSourceProperties.getUrl()` is right, it has not proven Hikari received that URL.

### 2.1. Default values in a class are not necessarily in Environment

If a `@ConfigurationProperties` class declares:

~~~java
private int maxConnections = 8;
~~~

then after binding, the object can return `8` even when the user did not declare the property. However, that **does not mean** `Environment.getProperty("acme.client.max-connections")` returns `"8"`.

A default declared on the object and a value present in `Environment` are two different concepts. When checking defaults, assert directly on the properties bean or the configured bean; do not merely query `Environment`.

## 3. Using ApplicationContextRunner to test auto-configuration in isolation

`ApplicationContextRunner` creates a small Spring ApplicationContext, giving control over:
- Which auto-configurations are loaded;
- Which properties are added to the Environment;
- Which user configurations or replacement beans are present;
- Which dependencies are present or missing on the classpath.

Each `.run(...)` call creates a separate context and closes it after the callback. Thus, tests do not have to boot the whole application or open HTTP ports.

Basic structure:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                DataSourceAutoConfiguration.class));

@Test
void configuredValuesReachTheDefaultBean() {
    contextRunner.withPropertyValues(
            "spring.datasource.url=jdbc:h2:mem:config_test",
            "spring.datasource.username=sa"
    ).run(context -> {
        // Assert the properties bean and the actual bean here.
    });
}
~~~

`withPropertyValues(...)` adds properties directly to the test context. This is a good way to isolate binding and conditions. However, it **does not by itself prove** that the production application loads `application.yml`, profiles, or environment variables properly; real Config Data testing is covered in section 10.

## 4. Complete example: testing Spring Boot's default DataSource

We check two groups of values:

- `spring.datasource.*`: URL, username, and password bound into `DataSourceProperties`.
- `spring.datasource.hikari.*`: pool configuration attached to `HikariDataSource`.

If these values reach the final bean, the application can inject `DataSource` and use the pool with the desired configuration.

### 4.1. Project structure

~~~text
datasource-binding-test/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── DataSourceAutoConfigurationTests.java
~~~

This is a standalone test; no `@SpringBootApplication` class or `main()` is needed.

### 4.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>datasource-binding-test</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>

        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-jdbc` provides Spring JDBC and HikariCP under the starter's default setup. H2 is in test scope only; it creates an in-memory database without installing or starting a database server.

If your project already has a parent/BOM managing the Spring Boot version, do not add a second parent; just add the missing dependencies.

### 4.3. Testing all values from properties to HikariDataSource

Create `src/test/java/example/DataSourceAutoConfigurationTests.java`:

~~~java
package example;

import com.zaxxer.hikari.HikariDataSource;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTests {

    private static final String JDBC_URL =
            "jdbc:h2:mem:config_binding_test";

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DataSourceAutoConfiguration.class));

    @Test
    void configuredPropertiesReachTheDefaultHikariDataSource() {
        contextRunner.withPropertyValues(
                "spring.datasource.url=" + JDBC_URL,
                "spring.datasource.username=sa",
                "spring.datasource.password=",
                "spring.datasource.hikari.maximum-pool-size=7",
                "spring.datasource.hikari.connection-timeout=3000"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            // Verify the properties bean.
            assertThat(context)
                    .hasSingleBean(DataSourceProperties.class);

            DataSourceProperties properties =
                    context.getBean(DataSourceProperties.class);

            assertThat(properties.getUrl()).isEqualTo(JDBC_URL);
            assertThat(properties.getUsername()).isEqualTo("sa");

            // Verify the actual default pool bean.
            assertThat(context).hasSingleBean(HikariDataSource.class);

            HikariDataSource dataSource =
                    context.getBean(HikariDataSource.class);

            assertThat(dataSource.getJdbcUrl()).isEqualTo(JDBC_URL);
            assertThat(dataSource.getUsername()).isEqualTo("sa");
            assertThat(dataSource.getMaximumPoolSize()).isEqualTo(7);
            assertThat(dataSource.getConnectionTimeout()).isEqualTo(3000L);
        });
    }
}
~~~

Assertions verify each layer:

1. `context.hasNotFailed()` confirms the context initialized successfully.
2. `DataSourceProperties` receives the URL and username from `spring.datasource.*`.
3. `HikariDataSource` is the actual pool implementation registered.
4. `getJdbcUrl()`, `getUsername()`, `getMaximumPoolSize()`, and `getConnectionTimeout()` confirm the values reached the final bean.

Notably, `maximum-pool-size` does not belong to `DataSourceProperties`; it is a Hikari-specific property. If you only checked `DataSourceProperties`, the test would miss pool configuration.

### 4.4. Running the test

With Maven:

~~~bash
mvn test -Dtest=DataSourceAutoConfigurationTests
~~~

With Maven Wrapper on macOS/Linux:

~~~bash
./mvnw test -Dtest=DataSourceAutoConfigurationTests
~~~

With Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=DataSourceAutoConfigurationTests'
~~~

Expected result: **1 test PASS**. Maven/Surefire output logs or report formatting may vary by version; what matters is that the test method passes with no assertion failures.

The test above verifies that configuration reaches the Hikari bean. It does not open a database connection yet. If your goal also includes verifying connection establishment, add an integration assertion with H2 as shown in section 9.

## 5. Checking default values when no property is declared

Sometimes the requirement is ensuring the default bean uses proper defaults when the user configures nothing.

Given an application-owned properties class:

~~~java
@ConfigurationProperties("acme.client")
public class AcmeClientProperties {

    private String endpoint = "https://api.example.test";

    private Duration connectTimeout = Duration.ofSeconds(2);

    private int maxConnections = 8;

    // Getters and setters for fields.
}
~~~

If the auto-configuration creates a bean from this object:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.getEndpoint(),
                properties.getConnectTimeout(),
                properties.getMaxConnections());
    }
}
~~~

then the default test must inspect both the properties object and the created bean:

~~~java
@Test
void defaultsReachTheDefaultClient() {
    clientContextRunner.run(context -> {
        assertThat(context).hasNotFailed();

        AcmeClientProperties properties =
                context.getBean(AcmeClientProperties.class);

        AcmeClient client = context.getBean(AcmeClient.class);

        assertThat(properties.getEndpoint())
                .isEqualTo("https://api.example.test");
        assertThat(properties.getConnectTimeout())
                .isEqualTo(Duration.ofSeconds(2));
        assertThat(properties.getMaxConnections()).isEqualTo(8);

        assertThat(client.endpoint())
                .isEqualTo(properties.getEndpoint());
        assertThat(client.connectTimeout())
                .isEqualTo(properties.getConnectTimeout());
        assertThat(client.maxConnections())
                .isEqualTo(properties.getMaxConnections());
    });
}
~~~

This is an illustrative snippet; `clientContextRunner` must be declared with `AutoConfigurations.of(AcmeClientAutoConfiguration.class)`, and `AcmeClient` needs the corresponding accessors.

**Why assert both sides?** If the properties bean has the right defaults yet the factory method accidentally passes the wrong field to the constructor, assertions on properties alone would still PASS. Only asserting on `AcmeClient` catches the wiring bug.

## 6. Testing when the application replaces the default bean

Many auto-configurations use `@ConditionalOnMissingBean` to let applications supply their own beans. When a user bean is present, the default bean backs off.

Example user configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomDataSourceConfiguration {

    @Bean
    DataSource customDataSource() {
        return new DriverManagerDataSource(
                "jdbc:h2:mem:custom_data_source",
                "sa",
                "");
    }
}
~~~

Add a test:

~~~java
@Test
void userDataSourceMakesTheDefaultPoolBackOff() {
    contextRunner
            .withUserConfiguration(CustomDataSourceConfiguration.class)
            .withPropertyValues(
                    "spring.datasource.url=jdbc:h2:mem:default_source",
                    "spring.datasource.username=sa")
            .run(context -> {
                assertThat(context).hasNotFailed();

                assertThat(context).hasSingleBean(DataSource.class);
                assertThat(context).hasBean("customDataSource");
                assertThat(context).doesNotHaveBean(HikariDataSource.class);
            });
}
~~~

This test confirms:
- The application-provided DataSource exists;
- The default Hikari DataSource is not registered;
- Auto-configuration respects the `@ConditionalOnMissingBean` extension point.

**Note:** when a user bean replaces the default DataSource, do not continue expecting `spring.datasource.url` to automatically configure the user-created `DriverManagerDataSource` bean. That bean was instantiated by the application's method; if you want to bind properties onto it, configure binding explicitly, such as placing `@ConfigurationProperties` on the `@Bean` method.

Do not use `@Primary` to hide an unwanted default bean in a back-off test. `@Primary` only picks the preferred bean for type-based injection; it does not prove that auto-configuration stopped creating the default bean.

## 7. Binding properties directly onto a third-party bean

Some libraries provide mutable JavaBeans without a dedicated `@ConfigurationProperties` class. Spring Boot lets you place the annotation directly on a `@Bean` method:

~~~java
@Bean
@ConditionalOnMissingBean
@ConfigurationProperties("acme.http")
ThirdPartyHttpClient thirdPartyHttpClient() {
    return new ThirdPartyHttpClient();
}
~~~

Suppose `ThirdPartyHttpClient` has:
- `setBaseUrl(String)`;
- `setReadTimeout(Duration)`;
- corresponding getters.

When the bean is created, the configuration properties binder binds `acme.http.*` keys onto the object. The test should retrieve **ThirdPartyHttpClient** and assert the getters on that object itself:

~~~java
contextRunner.withPropertyValues(
        "acme.http.base-url=https://partner.example.test",
        "acme.http.read-timeout=4s"
).run(context -> {
    ThirdPartyHttpClient client =
            context.getBean(ThirdPartyHttpClient.class);

    assertThat(client.getBaseUrl())
            .isEqualTo("https://partner.example.test");
    assertThat(client.getReadTimeout())
            .isEqualTo(Duration.ofSeconds(4));
});
~~~

This works well when integrating third-party libraries. If the bean is immutable or lacks setters, direct JavaBean binding may not fit; use a dedicated properties object and pass values via a constructor/builder or customizer.

## 8. Checking property sources, relaxed binding, and precedence

If tests produce different results from a real environment, check the value source before concluding the binder is broken.

### 8.1. Reading effective values in Environment

In tests or during diagnostics:

~~~java
String url = context.getEnvironment()
        .getProperty("spring.datasource.url");
~~~

This shows the property returned by Environment. Then compare it with `DataSourceProperties.getUrl()` and `HikariDataSource.getJdbcUrl()`.

Three values should align in a simple setup:

~~~text
Environment property
        |
        v
DataSourceProperties.url
        |
        v
HikariDataSource.jdbcUrl
~~~

If the three layers diverge, identify where the value changed:
- Which property source did Environment pick?
- Did the Binder bind the right field?
- Did the bean factory method use that properties object?
- Did a customizer or another configuration alter the bean after creation?

### 8.2. Relaxed binding

Spring Boot supports relaxed binding. For example, the property:

~~~properties
acme.client.connect-timeout=3s
~~~

can bind to the Java field `connectTimeout`.

For environment variables, canonical names convert according to the rules:
- dots become `_`;
- hyphens are removed;
- letters become uppercase.

Example:

~~~text
acme.client.connect-timeout
        |
        v
ACME_CLIENT_CONNECTTIMEOUT
~~~

When testing environment-variable property sources, follow this exact rule. Do not confuse it with naming conventions that insert an extra underscore between `CONNECT` and `TIMEOUT`.

### 8.3. Higher-precedence property sources

Spring Boot supports multiple configuration sources: application files, profile-specific files, environment variables, JVM system properties, and command-line arguments. Higher-precedence sources override lower-precedence ones.

Thus, if `application.yml` sets `maximum-pool-size: 10` but the runtime environment sets the corresponding environment variable to `7`, the final bean will receive `7`.

When debugging:
1. Inspect the value in `Environment`.
2. Identify the winning configuration source.
3. Check the value after binding.
4. Check the final bean.

Do not just read a YAML file and assume that is the running value.

## 9. Verifying real behavior when getters are insufficient

Some beans do not expose getters for every setting. In those cases, do not default to reflection to read private fields. Verify the public behavior that the configuration is expected to produce.

For example, with a DataSource, you can open a connection to in-memory H2 and run a query:

~~~java
@Test
void configuredDataSourceCanOpenAConnection() throws Exception {
    contextRunner.withPropertyValues(
            "spring.datasource.url=jdbc:h2:mem:connection_test",
            "spring.datasource.username=sa",
            "spring.datasource.hikari.maximum-pool-size=3"
    ).run(context -> {
        DataSource dataSource = context.getBean(DataSource.class);

        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement();
             ResultSet resultSet = statement.executeQuery("SELECT 1")) {

            assertThat(resultSet.next()).isTrue();
            assertThat(resultSet.getInt(1)).isEqualTo(1);
        }
        catch (SQLException exception) {
            throw new AssertionError(
                    "The configured DataSource could not execute SELECT 1",
                    exception);
        }
    });
}
~~~

Additional imports:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;
~~~

This test confirms the H2 connection actually works inside the test context. It does not test production database connectivity; integration tests for PostgreSQL/MySQL/Oracle still need an appropriate environment, typically Testcontainers or a dedicated test database.

## 10. When to use ApplicationContextRunner vs. SpringBootTest?

| Tool | Best suited when | Notes |
| --- | --- | --- |
| `ApplicationContextRunner` | Testing a single auto-configuration, properties, conditions, or bean back-off | Lightweight, easy to control; usually passes properties via `withPropertyValues` |
| `WebApplicationContextRunner` | Auto-configuration runs only in a servlet web context | Use when conditions depend on servlet context |
| `ReactiveWebApplicationContextRunner` | Auto-configuration depends on a reactive web context | Does not replace the servlet runner |
| `@SpringBootTest` | Testing multiple auto-configurations with the application, component scanning, and near-production config | Heavier, larger context |
| Integration tests with Testcontainers | Need to prove beans actually connect to production-compatible services/databases | Requires container runtime and longer execution time |

If the goal is **verifying values bound to default beans**, `ApplicationContextRunner` is usually the first choice. If you need to confirm `application.yml`, profiles, config trees, or command-line args load as in the real app, add a startup test via `SpringApplication` or `@SpringBootTest` with realistic configuration.

### @SpringBootTest example

~~~java
@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:spring_boot_test",
        "spring.datasource.username=sa",
        "spring.datasource.hikari.maximum-pool-size=5"
})
class DataSourceIntegrationTests {

    @Autowired
    DataSource dataSource;

    @Test
    void injectedDataSourceUsesConfiguredPool() {
        assertThat(dataSource)
                .isInstanceOf(HikariDataSource.class);

        HikariDataSource hikari =
                (HikariDataSource) dataSource;

        assertThat(hikari.getJdbcUrl())
                .isEqualTo("jdbc:h2:mem:spring_boot_test");
        assertThat(hikari.getMaximumPoolSize()).isEqualTo(5);
    }
}
~~~

The example above requires `@SpringBootApplication` in the test application or main sources so `@SpringBootTest` finds the boot configuration. It verifies the bean injected in a fuller application context, but should not replace small tests isolating each auto-configuration branch.

## 11. Testing validation and invalid configurations

If a properties class uses `@Validated`, invalid properties can prevent the context from starting.

Example:

~~~java
@ConfigurationProperties("acme.client")
@Validated
public class AcmeClientProperties {

    @NotBlank
    private String endpoint;

    @Min(1)
    private int maxConnections = 8;

    // Getters/setters.
}
~~~

An appropriate validation dependency is required, such as `spring-boot-starter-validation`.

Tests should cover both cases:
- Valid values create the context and bean;
- Invalid values cause context startup to fail with a clear validation cause.

With `ApplicationContextRunner`, you can inspect `context.getStartupFailure()` when the context fails to start. Do not merely assert that the bean is absent, because a missing bean could result from an unmatched condition or from the context failing before registering the bean.

## 12. Common mistakes and fixes

| Mistake | Why it is insufficient | Fix |
| --- | --- | --- |
| Asserting only the properties bean | The factory method might fail to use the right field | Also assert getters or behavior of the final bean |
| Asserting only bean existence | The bean might hold defaults or wrong property values | Assert concrete values on the bean |
| Checking `Environment` and assuming the bean is right | The bean might be built with other settings or altered by a customizer | Check Environment, properties object, and final bean |
| Checking defaults with `Environment.getProperty` | Class defaults are not necessarily added to Environment | Assert on the properties bean |
| Checking only `spring.datasource.*` | Misses `spring.datasource.hikari.*` | Assert pool-specific properties on `HikariDataSource` |
| User bean replaced default, yet test expects default bean | `@ConditionalOnMissingBean` makes auto-configuration back off | Write separate tests for custom beans and back-off |
| Using `@Primary` to hide extra beans | Does not prove the default bean backed off | Assert bean count and absence of default type/name |
| Expecting ApplicationContextRunner to auto-load application.yml | Runners usually receive properties directly, not full Config Data bootstrapping | Use SpringApplication/@SpringBootTest for Config Data |
| Using reflection to read private fields | Coupled to implementation, brittle across upgrades | Use getters or test public behavior |
| Testing only context startup | Bean may be created with wrong settings | Assert property values and perform real operations when needed |
| Testing against external databases | Tests depend on environment state | Use H2 or Testcontainers depending on the goal |

## 13. Step-by-step verification workflow

When a default bean has unexpected values:

1. **Identify the default bean:** its name, type, auto-configuration class, and factory method.
2. **Locate property prefixes:** inspect `@ConfigurationProperties`, `@ConfigurationProperties` on `@Bean`, or `Environment` reads.
3. **Separate shared vs. implementation-specific properties:** e.g., `spring.datasource.*` vs. `spring.datasource.hikari.*`.
4. **Create a small test context:** use `ApplicationContextRunner` and load only the target auto-configuration.
5. **Provide explicit test values:** use non-default values to catch missed binder/factory wiring.
6. **Assert the properties bean:** confirm the Binder converted values to the right types.
7. **Assert the final bean:** verify getters or actual behavior.
8. **Test default values:** omit properties and verify defaults on the object/bean.
9. **Test user overrides:** add a replacement bean and confirm the default bean backs off.
10. **Check real config sources:** if results differ from tests, inspect profiles, environment variables, command-line args, and Config Data.
11. **Run integration tests when needed:** verify connectivity or communication with real systems.

## 14. Self-check questions

**Question 1.** Why is asserting `DataSourceProperties.getUrl()` alone not enough?

**Answer:** Because the `DataSource` bean might not use those properties, or another configuration might replace the bean. You must assert the URL on the final DataSource implementation.

**Question 2.** Which property controls Hikari's maximum connection count?

**Answer:** `spring.datasource.hikari.maximum-pool-size`. This is a Hikari-specific setting, not a shared field in `DataSourceProperties`.

**Question 3.** Do defaults declared on `@ConfigurationProperties` fields necessarily appear in `Environment`?

**Answer:** No. Defaults may exist only on the object after binding; assert directly on the object.

**Question 4.** When an application provides its own DataSource, what can default auto-configuration do?

**Answer:** With `@ConditionalOnMissingBean(DataSource.class)`, Boot backs off and keeps the application-provided bean. Tests should verify the default bean is no longer registered.

**Question 5.** When should you use `ApplicationContextRunner` instead of `@SpringBootTest`?

**Answer:** When testing an auto-configuration with independently controlled properties, classpath, and user beans. Use `@SpringBootTest` when you need the full application context or real Config Data bootstrapping.

**Question 6.** If a bean has no getters for a setting, how should you verify it?

**Answer:** Verify the public behavior produced by that setting, such as opening a connection and running a query with a test DataSource. Avoid relying on private fields via reflection.

## 15. Official reference documentation

- Spring Boot 3.5 Reference — Externalized Configuration, `@ConfigurationProperties`, relaxed binding, default values, and property sources: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, Testing your Auto-configuration and `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 API — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.5 API — `DataSourceProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- HikariCP API — `HikariDataSource`: https://javadoc.io/doc/com.zaxxer/HikariCP/latest/com/zaxxer/hikari/HikariDataSource.html
