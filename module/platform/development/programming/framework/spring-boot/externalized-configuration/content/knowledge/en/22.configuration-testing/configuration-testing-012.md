# Distinguishing @DynamicPropertySource from @ServiceConnection with Testcontainers

## 1. The Problem: Letting Spring Boot Connect to a Dynamic Container

In integration tests, we often test the application against **PostgreSQL, MySQL, MongoDB, Redis, RabbitMQ**, or another service running in a container. Testcontainers provides test environments close to real infrastructure without manually installing every service on developer laptops.

For example, a PostgreSQL container may receive:

~~~text
host: localhost or container runtime host
mapped port: 49xxx, changing on every run
database: integration_test
username: test_user
password: test_password
~~~

Never hardcode connection URLs such as:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/integration_test
~~~

because Testcontainers maps ports dynamically and hosts vary across environments.

We need a mechanism to **supply the container's connection details** to the Spring Test ApplicationContext. In Spring Boot 3.3 there are two common approaches:

1. **@DynamicPropertySource** — supplies **dynamic properties** into the Spring Environment, such as **spring.datasource.url**, **spring.datasource.username**, **spring.datasource.password**, or **app.partner.base-url**.
2. **@ServiceConnection** — instructs Spring Boot to create **ConnectionDetails** from the container so supported auto-configurations connect directly to the service without manually declaring individual connection properties.

Both fit Testcontainers well, yet **they operate at two different layers**.

This lesson clarifies APIs, data flows, selection criteria, complete PostgreSQL examples, limits with custom services, lifecycle handling, and combined usage. Context is **Spring Boot 3.3.x**, **Spring Framework 6.1**, **JUnit 5**, and **Java 21**.

## 2. Learning Outcomes

After this lesson, you will be able to:

- Distinguish how **Spring Environment PropertySources** work compared to **ConnectionDetails**.
- Supply a dynamic URL/port/password from Testcontainers using **@DynamicPropertySource**.
- Write a **static** method accepting **DynamicPropertyRegistry** and registering **Supplier** callbacks.
- Apply **@ServiceConnection** on a container field or bean.
- Recognize the **spring-boot-testcontainers** dependency required by ServiceConnection.
- Understand how **JdbcConnectionDetails** is consumed by auto-configuration.
- Know why **spring.datasource.url** in Environment does not necessarily change when using ServiceConnection.
- Use **@ServiceConnection(name = "...")** when identifying a generically typed container.
- Combine both mechanisms when a test uses PostgreSQL alongside custom properties.
- Write tests proving the application genuinely connects to the container.
- Spot common bugs involving `static`, lifecycles, context caching, image matching, database replacement, and Docker runtimes.

**Short summary:** **@DynamicPropertySource registers properties**; **@ServiceConnection registers connection details for auto-configuration**. Do not treat them as two equivalent syntaxes for the exact same API.

## 3. Data-Flow Differences Diagram

### 3.1. @DynamicPropertySource

~~~text
Testcontainers PostgreSQL
  getJdbcUrl()
  getUsername()
  getPassword()
          |
          v
@DynamicPropertySource
DynamicPropertyRegistry.add(key, Supplier)
          |
          v
Spring Environment / PropertySource
  spring.datasource.url
  spring.datasource.username
  spring.datasource.password
          |
          v
Spring Boot DataSource auto-configuration
          |
          v
DataSource -> JDBC -> PostgreSQL container
~~~

Here, the test chooses **which key names Spring Boot receives** and pulls values from container getters.

### 3.2. @ServiceConnection

~~~text
Testcontainers PostgreSQL
        |
        v
@ServiceConnection
        |
        v
Matching ContainerConnectionDetailsFactory
        |
        v
JdbcConnectionDetails
        |
        v
Spring Boot DataSource auto-configuration
        |
        v
DataSource -> JDBC -> PostgreSQL container
~~~

Here, the test never registers **spring.datasource.url**, username, or password manually. Spring Boot recognizes the container, builds a **ConnectionDetails** bean, and supported auto-configurations consume it.

### 3.3. Key Consequences

- **@DynamicPropertySource** operates by **property name** in Environment.
- **@ServiceConnection** operates by **service type and ConnectionDetails type** supported by Spring Boot.
- With ServiceConnection, **connection details take precedence over connection-related configuration properties** when consumed by auto-configuration.
- That **does not mean** ServiceConnection overwrites **spring.datasource.url** in Environment.
- If your application code calls **Environment.getProperty("spring.datasource.url")** directly, the result does not necessarily reflect the connection used by DataSource under ServiceConnection.
- If your application reads custom keys like **app.partner.base-url**, ServiceConnection helps only if a matching integration/ConnectionDetails exists; **@DynamicPropertySource** is usually simpler.

## 4. Preparing Dependencies

A complete example using **real PostgreSQL in Testcontainers** and **JdbcTemplate** running **SELECT 1**.

### 4.1. Gradle

Assuming the project uses Spring Boot 3.3.x and Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Purpose:

- **spring-boot-starter-jdbc**: JDBC, DataSource, and JdbcTemplate support.
- **org.postgresql:postgresql**: PostgreSQL JDBC driver.
- **spring-boot-starter-test**: Spring Boot Test, JUnit 5, AssertJ.
- **org.testcontainers:junit-jupiter**: Testcontainers JUnit Jupiter integration.
- **org.testcontainers:postgresql**: dedicated PostgreSQL container module.
- **spring-boot-testcontainers**: Spring Boot **@ServiceConnection** and connection details factories.

When using the Spring Boot BOM/dependency management, you generally do not need manual versions on each dependency above.

**Using only @DynamicPropertySource** does not require **spring-boot-testcontainers**; that annotation belongs to Spring TestContext Framework. To compare both in the same project, we include this dependency.

### 4.2. Maven

Dependencies for a project using the Spring Boot parent or BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If using **@DataJpaTest** and JPA repositories instead of JdbcTemplate, include **spring-boot-starter-data-jpa** matching your architecture. Do not add the JPA starter if tests only need JDBC.

### 4.3. Runtime Requirements for Testcontainers

Testcontainers requires a compatible **container runtime**, typically Docker. CI agents must have permission to access that runtime.

Check first:

~~~bash
docker version
docker info
~~~

If these fail to reach the Docker daemon, Testcontainers tests will fail to start containers.

On developer machines, Docker Desktop or a compatible runtime must be running. On CI, configure socket permissions and networking; do not assume every runner has Docker out of the box.

## 5. Minimal Test Application

Main class:

~~~java
package com.example.tc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestcontainersDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                TestcontainersDemoApplication.class, args);
    }
}
~~~

The tests use **JdbcTemplate**, auto-configured by Spring Boot once DataSource can initialize.

No entities, tables, or web server are required. The query:

~~~sql
SELECT 1
~~~

is enough to prove a real JDBC connection reached the PostgreSQL container.

### 5.1. Typical Configuration File

An **application.yml** for local development might contain:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/localdb"
    username: local_user
    password: local_password
~~~

In integration tests, we must avoid connecting to that local database by mistake. Both techniques in this lesson point the test DataSource to the container, through **two distinct configuration paths**.

**Never use real production passwords** in test examples. Container accounts/credentials here exist solely for ephemeral test databases.

## 6. Approach 1 — @DynamicPropertySource with PostgreSQLContainer

**@DynamicPropertySource** is provided by Spring Framework in:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
~~~

It lets a test register dynamic property values, ideal for containers whose host or port is assigned after startup.

Complete example:

~~~java
package com.example.tc;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class DynamicPostgresIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_test")
                .withUsername("test_user")
                .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
                "spring.datasource.url", postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username", postgres::getUsername);
        registry.add(
                "spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void connectsToContainer() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

Step-by-step breakdown:

1. **@Testcontainers** activates the JUnit Jupiter extension managing Testcontainers.
2. **@Container** marks the container instance managed by the extension.
3. The **static** field shares one container across test methods in the class.
4. **PostgreSQLContainer** exposes the real JDBC URL, username, and password after starting.
5. **@DynamicPropertySource** marks the method registering dynamic properties.
6. That method is **static** and takes one **DynamicPropertyRegistry** parameter.
7. **registry.add(key, Supplier)** registers value providers; method references like **postgres::getJdbcUrl** avoid calling getters prematurely at registration time.
8. DataSource auto-configuration reads **spring.datasource.*** and builds the JDBC DataSource.
9. **JdbcTemplate** queries the container, proving live connectivity.

### 6.1. Why Not Hardcode localhost:5432?

Testcontainers maps PostgreSQL's internal port **5432** to an arbitrary host port. **postgres.getJdbcUrl()** returns the JDBC URL matching the active host and mapped port.

For example, one run might get:

~~~text
jdbc:postgresql://localhost:49215/integration_test
~~~

The next run gets another port. This is an example value, **not a fixed port to configure**.

### 6.2. Why Supplier Matters

Instead of passing a precomputed value:

~~~java
registry.add(
        "spring.datasource.url", () -> postgres.getJdbcUrl());
~~~

you can pass a method reference:

~~~java
registry.add(
        "spring.datasource.url", postgres::getJdbcUrl);
~~~

Both supply a **Supplier**. Spring Test invokes the Supplier when resolving the property rather than demanding the value at registration time.

**@DynamicPropertySource** methods should never make heavy network calls or start services unexpectedly. Keep container lifecycles managed explicitly.

## 7. API and Rules for @DynamicPropertySource

A valid method looks like:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("app.external.host", server::getHost);
}
~~~

Core constraints:

- Annotation sits on a **method**, not a class or field.
- Method must be **static**.
- Method takes a single parameter of type **DynamicPropertyRegistry**.
- **registry.add(name, supplier)** requires a property name and a Supplier.
- Multiple keys can be registered in the same method.
- Dynamic properties are added to the Spring TestContext **Environment**.

Do not confuse with:

~~~java
@TestPropertySource(properties = "spring.datasource.url=...")
~~~

**@TestPropertySource** works for static values. **@DynamicPropertySource** works when values come from a service whose host/port is known only at runtime.

### 7.1. Precedence of Dynamic Properties

Spring Framework explicitly specifies that dynamic properties have **higher** precedence than **@TestPropertySource**, OS environment variables, Java system properties, and standard PropertySources.

For example, if a test has:

~~~java
@TestPropertySource(properties = {
    "spring.datasource.url=jdbc:postgresql://wrong-host:5432/wrong"
})
~~~

yet the dynamic method registers:

~~~java
registry.add(
        "spring.datasource.url", postgres::getJdbcUrl);
~~~

when Environment resolves **spring.datasource.url**, the dynamic property wins.

**Do not view this as absolute priority over every connection mechanism**, because **@ServiceConnection** is not simply another PropertySource. Keep property precedence distinct from ConnectionDetails precedence.

### 7.2. Checking the Value Registered in Environment

In a DynamicPropertySource test:

~~~java
@Autowired
Environment environment;

@Test
void publishesJdbcUrl() {
    assertThat(environment.getProperty(
                "spring.datasource.url"))
            .startsWith("jdbc:postgresql:");
}
~~~

This checks that **the property was registered in Environment**. The **SELECT 1** test in section 6 checks that **DataSource actually works**. Both assertions serve different purposes.

**Never log passwords**, even when registered in Environment.

## 8. Using @DynamicPropertySource for Custom Application Keys

A major advantage is **independence from the list of services for which Spring Boot ships a ConnectionDetails factory**.

Suppose the application defines:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        Duration requestTimeout) {
}
~~~

And an HTTP test server/container binds a random port. You can register:

~~~java
@DynamicPropertySource
static void partnerProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.partner.base-url",
            () -> "http://" + partner.getHost()
                    + ":" + partner.getMappedPort(80));

    registry.add(
            "app.partner.request-timeout",
            () -> "2s");
}
~~~

This snippet assumes the test class defines and starts **partner** as a Testcontainers **GenericContainer** exposing port **80**.

**app.partner.base-url** is not a standard Spring Boot connection key, yet it is a valid property defined by your application code.

With **@ServiceConnection**, without a matching ConnectionDetails factory and auto-configuration for that partner service, simply adding the annotation cannot update **app.partner.base-url**.

### 8.1. Flow for Custom Properties

~~~text
Testcontainer HTTP mock
     |
     v
partner.getHost() + partner.getMappedPort(80)
     |
     v
DynamicPropertyRegistry
  app.partner.base-url
     |
     v
Environment
     |
     v
PartnerProperties.baseUrl
     |
     v
Application's PartnerClient
~~~

This is why you should not abandon **@DynamicPropertySource** just because **@ServiceConnection** has shorter syntax for PostgreSQL or Redis.

## 9. Approach 2 — @ServiceConnection with PostgreSQLContainer

**@ServiceConnection** is **Spring Boot**'s Testcontainers integration. It lets auto-configuration derive connection details from a container via **ConnectionDetails**.

Import:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
~~~

Dependency:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
~~~

Complete example:

~~~java
package com.example.tc;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class ServiceConnectionPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_test")
                .withUsername("test_user")
                .withPassword("test_password");

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void connectsToContainer() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

Notable difference: **no @DynamicPropertySource** and **no three `registry.add(...)` calls**.

Spring Boot inspects the **@ServiceConnection**-annotated container and creates a matching ConnectionDetails bean. For PostgreSQL JDBC, auto-configuration consumes **JdbcConnectionDetails** to build DataSource.

### 9.1. Two Annotations with Two Responsibilities

In the example:

~~~java
@Testcontainers
...
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres = ...;
~~~

- **@Testcontainers** and **@Container** belong to JUnit/Testcontainers and manage container lifecycle.
- **@ServiceConnection** belongs to Spring Boot and wires auto-configuration to the container.

**@ServiceConnection does not replace @Container for lifecycle management** in this static-field pattern. Conversely, **@Container** does not create JdbcConnectionDetails for Spring Boot.

### 9.2. @ServiceConnection Works Through ConnectionDetails

**ConnectionDetails** is an abstraction carrying details required to connect to a service. A common type is **JdbcConnectionDetails**.

Instead of relying solely on:

~~~properties
spring.datasource.url=...
spring.datasource.username=...
spring.datasource.password=...
~~~

auto-configuration pulls connection parameters from the JdbcConnectionDetails bean.

For service connections created from Testcontainers, these connection details take priority over connection-related configuration properties when consumed by supported auto-configurations.

That is why tests no longer need to copy URL, username, and password from the container into Environment manually.

## 10. @ServiceConnection Does Not Simply Write to Environment

This is an important distinction that often causes confusion.

Suppose **application.yml** sets:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/localdb
~~~

and the test declares:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

When supported auto-configuration consumes **JdbcConnectionDetails** from the container, DataSource connects to the container **even though Environment still reports spring.datasource.url as the local URL**.

Therefore:

~~~java
String url = environment.getProperty("spring.datasource.url");
~~~

is **not necessarily the JDBC URL DataSource is using** under ServiceConnection.

To verify the actual connection, use:

- A simple query via JdbcTemplate.
- Inspecting DataSource/Connection metadata inside the test.
- Inspecting the JdbcConnectionDetails bean when diagnosing issues.

**Never write a test asserting Environment.getProperty("spring.datasource.url") equals container.getJdbcUrl() as a requirement for @ServiceConnection.** That tests a behavior ServiceConnection never promises.

### 10.1. Example: Inspecting the Real DataSource

~~~java
@Autowired
DataSource dataSource;

@Test
void usesContainerDatabase() throws Exception {
    try (Connection connection =
            dataSource.getConnection()) {

        String actualUrl =
                connection.getMetaData().getURL();

        assertThat(actualUrl)
                .contains("integration_test");
    }
}
~~~

Imports:

~~~java
import java.sql.Connection;
import javax.sql.DataSource;
~~~

JDBC driver metadata reflects the connection's real URL. This assertion tests real connectivity rather than peeking at raw Environment properties.

In multi-DataSource systems, ensure you inject and inspect the specific DataSource bean under test.

## 11. Quick Comparison of Both Annotations

| Criterion | @DynamicPropertySource | @ServiceConnection |
| --- | --- | --- |
| Provided by | **Spring Framework TestContext** | **Spring Boot Testcontainers** |
| Placed on | **static method** | **container field** or **@Bean** container |
| Core API | **DynamicPropertyRegistry.add(key, Supplier)** | **ConnectionDetails factories** |
| Data unit | Named property in Environment | ConnectionDetails bean for a service |
| Must know key names | Yes, chosen by test | No for factory-supported services |
| JDBC URL/username/password | Register each key manually | Derived from PostgreSQLContainer automatically |
| Custom `app.*` properties | Supported directly | Not supported without custom factory/consumer |
| Precedence rule | High priority in Environment | ConnectionDetails beats connection properties in supported consumers |
| Extra dependency | Spring TestContext (via starter-test) | **spring-boot-testcontainers** |
| Proper verification | Environment key and client behavior | ConnectionDetails and client behavior |
| Applicability | Broad: any property key | Primarily services with ConnectionDetails factories |
| JDBC boilerplate | Register url, username, password | Add annotation; zero key registration |
| Usable together | Yes | Yes |

**Selection rule:** If a service has a ServiceConnection factory and the app uses ConnectionDetails-aware auto-configuration, **@ServiceConnection** is cleaner. When supplying **custom property names**, **@DynamicPropertySource** is the right fit.

## 12. Which Services Are Commonly Recognized by @ServiceConnection?

Spring Boot 3.3 ships **ContainerConnectionDetailsFactory** implementations for many containers and services.

Typical examples:

- **PostgreSQLContainer**, **MySQLContainer**, and compatible JDBC database containers provide **JdbcConnectionDetails**.
- **MongoDBContainer** provides **MongoConnectionDetails**.
- **RabbitMQContainer** provides **RabbitConnectionDetails**.
- **Neo4jContainer** provides **Neo4jConnectionDetails**.
- Kafka/Redpanda containers have factories matching supported client libraries.
- Container images with repository **redis** are recognized for **RedisConnectionDetails**.
- Additional integrations like Flyway, Liquibase, and R2DBC have matching factories depending on the container.

**Not every GenericContainer is automatically recognized.** Factory matching can depend on:

1. Specific **container class**, e.g. PostgreSQLContainer.
2. **Docker image name**, e.g. repository **redis**.
3. **@ServiceConnection(name = "...")** as a hint for container/image type when appropriate.

Check the exact API and factory list for your **Spring Boot version**. Do not assume the annotation creates ConnectionDetails for arbitrary custom images.

### 12.1. PostgreSQL Can Relate to Multiple ConnectionDetails Types

Spring Boot 3.3 documents that a PostgreSQLContainer can match both **JdbcConnectionDetails** and **R2dbcConnectionDetails**.

By default, matching connection details beans can be produced for the container. Which service connection is actually **consumed** depends on the classpath and application auto-configurations.

Examples:

- JDBC projects consume JdbcConnectionDetails.
- Reactive R2DBC projects consume R2dbcConnectionDetails.
- Projects without R2DBC will not suddenly create an R2DBC client just because a ConnectionDetails of that type exists.

When you need to restrict the generated type, **@ServiceConnection** supports a **type** attribute to specify which connection details class to produce.

### 12.2. @ServiceConnection(type = ...)

Example restricting to JDBC only:

~~~java
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

@ServiceConnection(type = JdbcConnectionDetails.class)
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Use this only when you specifically need to constrain factory output. In simple JDBC setups, bare **@ServiceConnection** is usually sufficient.

## 13. @ServiceConnection on a Container @Bean

Besides static fields on JUnit tests, Spring Boot supports containers registered as Spring beans.

Test configuration example:

~~~java
package com.example.tc;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgreSqlTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_test")
                .withUsername("test_user")
                .withPassword("test_password");
    }
}
~~~

Test importing the configuration:

~~~java
package com.example.tc;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(PostgreSqlTestConfiguration.class)
class SpringManagedContainerTest {

    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void canQueryDatabase() {
        Integer answer = jdbcTemplate.queryForObject(
                "SELECT 1", Integer.class);
        assertThat(answer).isEqualTo(1);
    }
}
~~~

Here, Spring Boot manages the container **as a bean** inside the test ApplicationContext. The container bean starts per Boot-managed lifecycle and stops when the context closes.

**Do not add @Testcontainers / @Container** for a container **@Bean** already managed by Spring Boot. Avoid mixing both lifecycle mechanisms unnecessarily.

### 13.1. When to Choose a Container Bean?

Best when:

- Multiple test classes share test configuration via **@Import**.
- You want the container's lifecycle tied to the Spring ApplicationContext.
- You are building reusable test configuration in a module.
- You want to combine container management with dependent beans.

Keep **Spring TestContext caching** in mind: the container bean lives alongside the cached context and stops when the context closes. By contrast, JUnit-managed field containers follow a different lifecycle, creating risks if a cached context holds a connection bean pointing to a stopped container.

## 14. Why a GenericContainer @Bean May Need name

For a specific container type:

~~~java
@Bean
@ServiceConnection
PostgreSQLContainer<?> postgresContainer() {
    return new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Spring Boot sees the return type is **PostgreSQLContainer** and can infer the matching factory.

With a bean returning:

~~~java
@Bean
@ServiceConnection
GenericContainer<?> redisContainer() {
    return new GenericContainer<>("redis:7");
}
~~~

Spring Boot cannot invoke the bean method early just to inspect the image name, because that would cause **eager initialization**. The **GenericContainer** type alone is not enough to identify Redis.

Proper setup:

~~~java
package com.example.tc;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.GenericContainer;

@TestConfiguration(proxyBeanMethods = false)
public class RedisTestConfiguration {

    @Bean
    @ServiceConnection(name = "redis")
    GenericContainer<?> redisContainer() {
        return new GenericContainer<>("redis:7")
                .withExposedPorts(6379);
    }
}
~~~

**name = "redis"** gives a hint to the factory. For `RedisConnectionDetails` to actually be consumed by auto-configuration, the app must include matching Redis client dependencies/auto-configurations; this class illustrates registration only.

### 14.1. Custom Registry Images/Mirrors

Suppose a company uses an image like:

~~~text
registry.company.invalid/mirror/redis-custom:7
~~~

If the factory does not recognize the custom image repository, use:

~~~java
@ServiceConnection(name = "redis")
~~~

to declare it as a Redis-compatible service, provided the image actually speaks the Redis protocol on the expected port.

**Never supply an arbitrary name just to force a factory to run** if the container is not actually protocol-compatible with that service.

## 15. Spring Boot ServiceConnection and @ConfigurationProperties

Suppose a configuration defines:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        String apiKey) {
}
~~~

If a test launches a **GenericContainer** running a mock partner service, **@ServiceConnection** will not locate PartnerProperties and populate **baseUrl**. This annotation is not a generic replacement for **@ConfigurationProperties binding**.

By contrast, **@DynamicPropertySource** feeds values into that model via canonical keys:

~~~java
registry.add(
        "app.partner.base-url",
        () -> "http://" + partner.getHost()
                + ":" + partner.getMappedPort(80));
~~~

Spring Boot Binder then binds it into PartnerProperties just like any other property.

**Distinguish the two paths:**

~~~text
@DynamicPropertySource
    -> Environment key
    -> @ConfigurationProperties / @Value / DataSourceProperties

@ServiceConnection
    -> ConnectionDetails bean
    -> Auto-configuration supporting ConnectionDetails
~~~

A system can implement **custom ConnectionDetails** for proprietary services, yet that is separate infrastructure work—not automatic behavior from placing the annotation on any container.

## 16. Combining Both Approaches in the Same Test

Realistic scenario: an application uses **PostgreSQL** managed by Spring Boot DataSource auto-configuration, plus a **mock HTTP service** whose base URL application code reads via **app.partner.base-url**.

Choices:

- PostgreSQL -> **@ServiceConnection**.
- HTTP mock -> **@DynamicPropertySource**.

Example:

~~~java
package com.example.tc;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class MixedConnectionsTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    static GenericContainer<?> partner =
            new GenericContainer<>("nginx:1.27-alpine")
                .withExposedPorts(80);

    @DynamicPropertySource
    static void partnerProperties(
            DynamicPropertyRegistry registry) {

        registry.add("app.partner.base-url", () ->
                "http://" + partner.getHost()
                        + ":" + partner.getMappedPort(80));
    }

    @Test
    void contextStarts() {
        // In a real app:
        // assert PartnerProperties and query the DB or HTTP mock.
    }
}
~~~

This example uses an Nginx container solely to illustrate an HTTP endpoint with a mapped port. When your app needs specific API responses, use **WireMock**, **MockServer**, or a mock container configured for that API contract.

**The two annotations do not conflict in the same test.** They fulfill distinct roles: standard connection details vs. custom properties.

### 16.1. Avoid Wiring Both Mechanisms to the Same JDBC Connection Unnecessarily

For instance, putting both:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> postgres = ...;
~~~

and:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

in the same test.

It may still run, yet creates **two competing configuration paths** for the same connection. Because JdbcConnectionDetails takes priority, adding the extra property creates confusion when debugging.

**Recommendation:** pick one authoritative mechanism per service unless specifically testing precedence.

## 17. Using @DynamicPropertySource with Containers Unsupported by Boot

Not every Testcontainers module has a built-in factory in Spring Boot 3.3.

A custom service may listen on:

~~~text
http://<host>:<mapped-port>
~~~

while the application reads:

~~~properties
app.search.endpoint=...
app.search.token=...
~~~

A test can register:

~~~java
@DynamicPropertySource
static void dynamicSearchProperties(
        DynamicPropertyRegistry registry) {

    registry.add("app.search.endpoint", () ->
            "http://" + searchContainer.getHost()
                    + ":" + searchContainer.getMappedPort(8080));

    registry.add("app.search.token",
            () -> "test-only-token");
}
~~~

This assumes **searchContainer** is already defined/started and exposes port 8080.

Its strength is that the property mechanism **does not need to recognize the container type**. It just supplies whatever values the application expects.

If the application defines:

~~~java
@ConfigurationProperties(prefix = "app.search")
public record SearchProperties(
        URI endpoint,
        String token) {
}
~~~

Binder populates this object from the dynamic properties when the bean initializes.

### 17.1. Test Tokens Are Not Production Secrets

Use dummy credentials solely for test containers. Never copy production API tokens into JUnit sources or unprotected CI variables, and never print tokens to logs even in tests.

## 18. Precedence: Properties and ConnectionDetails Are Two Separate Axes

Keep these distinct:

### 18.1. Dynamic Properties Have High Precedence in Environment

Suppose:

~~~java
@TestPropertySource(properties = {
    "spring.datasource.url=jdbc:postgresql://wrong-host/db"
})
~~~

and:

~~~java
@DynamicPropertySource
static void postgresProps(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl);
}
~~~

Spring TestContext gives the dynamic property priority when resolving **spring.datasource.url**.

### 18.2. ServiceConnection Uses ConnectionDetails

If you replace the method above with:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> postgres = ...;
~~~

auto-configuration consumes **JdbcConnectionDetails** from the container. This is not "a higher-priority property source" in the same sense as DynamicPropertySource.

Thus there are two separate questions:

1. **What string does Environment resolve `spring.datasource.url` to?**
2. **Where is DataSource auto-configuration getting its JDBC connection details?**

To verify the actual database in use, the second question—or a real SQL query—is what matters.

### 18.3. Example False Positive When Inspecting Environment

A test using ServiceConnection can observe:

~~~text
Environment:
  spring.datasource.url = some local/default value

DataSource:
  connected to Testcontainers PostgreSQL
~~~

There is no contradiction here. ConnectionDetails directed auto-configuration to the container while Environment properties retained their static values.

## 19. Container and Test Class Lifecycles

When using:

~~~java
@Testcontainers
class ExampleTest {
    @Container
    static PostgreSQLContainer<?> postgres = ...;
}
~~~

the JUnit Testcontainers extension manages the static field within the test class's scope:

- The static container is shared across test methods in that class.
- Typically the container starts before test methods and stops after the class completes.
- Spring TestContext can **cache the ApplicationContext** for reuse across test classes.
- The static JUnit container lifecycle and the cached context lifecycle **do not necessarily match**.

If a cached context retains a DataSource pointing to a stopped container, subsequent tests fail even when initial configuration was right.

### 19.1. Reducing Lifecycle Risks

- Choose container lifecycle explicitly: JUnit field vs. Spring-managed bean.
- Avoid sharing ApplicationContexts across test classes with different containers whose configuration metadata looks identical.
- For test subclasses inheriting **@DynamicPropertySource** whose dynamic values change, consider **@DirtiesContext** per Spring Framework guidance.
- When using a Spring-managed **@Bean** container, remember it lives with the test context and stops when the context closes.
- Never manually start/stop a container inside each `@Test` if the Spring context is built once and beans already connected earlier.
- In large suites, establish clear reuse, isolation, and cleanup policies.

### 19.2. When Is @DirtiesContext Unnecessary?

Do not slap **@DirtiesContext** onto every test mechanically. It disables context reuse, slows tests down, and can trigger extra container startups.

Use it only when context state or dynamic property values genuinely change between tests and require a fresh context.

## 20. Combining with @SpringBootTest

Both main examples use:

~~~java
@SpringBootTest
@Testcontainers
~~~

**@SpringBootTest** loads the Spring Boot application context, giving tests real DataSource and auto-configuration behavior.

**@Testcontainers** manages field-level container lifecycles.

**@DynamicPropertySource** or **@ServiceConnection** supplies connection info.

If a test actually needs a running REST server, use:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
~~~

and pair with appropriate HTTP test utilities.

Do not spin up an embedded server if the test only runs JDBC queries. Choose `webEnvironment` intentionally to avoid needless overhead.

### 20.1. @DynamicPropertySource Is Not Limited to SpringBootTest

This annotation belongs to **Spring TestContext Framework**, so it works across any TestContext-supported Spring integration test style.

### 20.2. @ServiceConnection Is Also Not Tied to One Test Annotation

It works with Spring Boot test slices or container beans inside test configurations, provided the required infrastructure and auto-configurations are loaded.

What matters is **whether the test creates and consumes the connection details**.

## 21. @DataJpaTest and DataSource Replacement in Test Slices

If you replace JdbcTemplate with JPA repositories, you might write:

~~~java
@DataJpaTest
@Testcontainers
class RepositoryTest {
    ...
}
~~~

However, **@DataJpaTest** is a test slice configured for persistence testing and may swap the DataSource for an embedded test database under default rules.

To ensure the test uses PostgreSQL Testcontainers rather than an embedded database, add:

~~~java
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
~~~

Example:

~~~java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired repositories and test persistence behavior.
}
~~~

Imports:

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
~~~

**Note:** exact DataSource replacement details and ServiceConnection behavior in slices depend on Spring Boot version and setup. Use **replace=NONE** to explicitly prevent replacing the container connection with an embedded DB, and assert against the real database.

### 21.1. Why Testing Real PostgreSQL Matters

SQL dialects, data types, indexes, and transaction behaviors differ between PostgreSQL and H2/HSQLDB. Repository tests running on embedded DBs do not always reflect production PostgreSQL accurately.

Testcontainers provides the real backend in an isolated environment, making schema, migration, and query tests far more reliable.

## 22. Verifying the Real DataSource Instead of Only Context Startup

A weak test:

~~~java
@Test
void contextLoads() {
}
~~~

The context may start without ever running a query against the intended backend.

A stronger test:

~~~java
@Autowired
JdbcTemplate jdbc;

@Test
void runsQueryOnContainer() {
    Integer value = jdbc.queryForObject(
            "SELECT 1", Integer.class);

    assertThat(value).isEqualTo(1);
}
~~~

Or:

~~~java
@Autowired
DataSource dataSource;

@Test
void connectsToExpectedDatabase() throws Exception {
    try (Connection connection =
            dataSource.getConnection()) {

        assertThat(connection.getMetaData()
                .getURL())
                .contains("integration_test");
    }
}
~~~

These assertions catch misconfigured overrides or an unexpected DataSource being created.

**Never check only `container.isRunning()`.** A running container does not prove Spring beans actually connected to it.

## 23. When Is @ServiceConnection(name=...) Needed?

A Redis example:

~~~java
@Testcontainers
@SpringBootTest
class RedisIntegrationTest {

    @Container
    @ServiceConnection(name = "redis")
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7")
                .withExposedPorts(6379);

    // Autowire RedisTemplate when a matching Redis starter is present.
}
~~~

On a static field, Boot can inspect the image name and match a factory by repository. **name="redis"** makes identity explicit, especially with generic or custom images.

On a **`@Bean` method returning `GenericContainer`**, `name` is often required because Spring Boot will not invoke the bean method early just to inspect its image name.

If the container speaks another protocol or Redis is not listening on port 6379, adding `name` alone will not make the client succeed. ServiceConnection does not replace proper container configuration and network readiness.

## 24. When a Service Has Multiple Endpoints or Custom Authentication

A custom container may expose:

- HTTP host + port.
- gRPC port.
- TLS endpoint.
- Username/password.
- API token.
- Separate admin and data endpoints.

With **@DynamicPropertySource**, register custom keys explicitly:

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.service.http-url",
            () -> "http://" + service.getHost()
                    + ":" + service.getMappedPort(8080));
    registry.add(
            "app.service.grpc-port",
            () -> service.getMappedPort(9090));
    registry.add(
            "app.service.token",
            () -> "test-token");
}
~~~

This assumes the container exposes both ports. **app.service.*** is an application-defined namespace.

To reach similar integration with **@ServiceConnection**, you would need a ConnectionDetails abstraction and factory consumed by auto-configuration. Do not expect Boot to auto-discover arbitrary endpoints on a GenericContainer.

## 25. Testing a Context with Both Override Mechanisms

Suppose:

**application-test.yml**:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/static_test_db"
    username: static_user
    password: static_password

app:
  partner:
    base-url: "http://localhost:9000"
~~~

In the test:

- **@ServiceConnection** points JDBC DataSource to PostgreSQLContainer.
- **@DynamicPropertySource** overrides **app.partner.base-url** to the HTTP mock container.

Expected outcome:

~~~text
DataSource:
    uses JdbcConnectionDetails from PostgreSQLContainer

PartnerProperties:
    baseUrl binds from app.partner.base-url
    supplied by DynamicPropertySource

Environment.getProperty("spring.datasource.url"):
    may still return the static URL from application-test.yml
~~~

This state is completely valid and shows the two mechanisms cooperating rather than conflicting.

### 25.1. Do Not Infer Every Connection from Environment

A bean may receive connection details from a source higher than properties. When debugging, identify the exact consumer:

- DataSource.
- R2DBC ConnectionFactory.
- MongoClient.
- Rabbit connection factory.
- Redis client.
- Custom application client.

Then check whether it reads Environment or ConnectionDetails.

## 26. Notes for Running in CI

Testcontainers requires a container runtime able to pull/run images, publish/map ports, and allow network access.

CI checklist:

1. Does the runner have Docker or a compatible runtime?
2. Does the test user have daemon/socket permissions per security policy?
3. Can **postgres:16-alpine** be pulled or is it cached?
4. Does the registry impose rate limits or require authentication?
5. Do network policies block access to mapped ports?
6. Are Testcontainers dependency versions aligned with the Spring Boot BOM?
7. Do container health/startup readiness checks have reasonable timeouts?
8. Do parallel tests exhaust memory or CPU?
9. Is database cleanup/isolation clear across test methods?
10. Could tests accidentally touch production databases or real credentials?
11. Do logs capture useful diagnostics if a container fails to start?
12. Could context caching / container lifecycle mismatches break the suite?

### 26.1. Never Bind Fixed Host Ports Unnecessarily

If every test tries binding host port 5432, parallel CI jobs collide and machines with local PostgreSQL fail.

Let Testcontainers assign dynamic mapped ports; retrieve endpoints via getters or ServiceConnection.

### 26.2. Image Versions

Examples use **postgres:16-alpine** for illustration. In real projects, pick a PostgreSQL version close to production, update deliberately, and follow team reproducibility policies.

Avoid unpinned **latest** tags when deterministic test results matter over time.

## 27. Troubleshooting: @DynamicPropertySource Is Not Invoked

Symptoms:

- DataSource still uses the local URL.
- Context fails unable to connect to localhost:5432.
- Dynamic properties appear ignored.

Check:

- Does the method carry **@DynamicPropertySource** from Spring Test's package?
- Is the method **static**?
- Does it accept a single **DynamicPropertyRegistry** parameter?
- Does the test execute through Spring TestContext (e.g. **@SpringBootTest**)?
- Are key names exact (**spring.datasource.url**, **username**, **password**)?
- Is the container field managed and started in the right lifecycle?
- Does a custom DataSource bean ignore those properties?

Wrong example:

~~~java
@DynamicPropertySource
void register(DynamicPropertyRegistry registry) {
    // Wrong: method is not static.
}
~~~

Right example:

~~~java
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    // ...
}
~~~

## 28. Troubleshooting: @ServiceConnection Has No Effect

Symptoms:

- DataSource does not point to the container.
- Expected ConnectionDetails bean does not exist.
- Spring Boot still demands `spring.datasource.url` or connection properties.
- Spring Boot fails to recognize a GenericContainer.

Check:

1. Is **spring-boot-testcontainers** in **testImplementation / test scope**?
2. Is the annotation imported from **org.springframework.boot.testcontainers.service.connection.ServiceConnection**?
3. Is the container declared as a static field or properly processed Spring bean?
4. Does a factory exist for that container class in your Spring Boot version?
5. If using a **GenericContainer @Bean**, is **name="redis"** or a recognized image name needed?
6. Are auto-configuration and client dependencies present (e.g. JDBC starter + PostgreSQL driver)?
7. Does the app define a custom DataSource bypassing ConnectionDetails?
8. Did the container actually start and expose the right protocol/port?
9. Is a test slice replacing DataSource with an embedded DB?
10. With multiple containers of the same type, is auto-configuration picking the right bean/service?

Do not stack random annotations hoping it works. Identify whether the gap lies in **container lifecycle**, **factory matching**, **ConnectionDetails bean**, or **client auto-configuration**.

## 29. Common Pitfalls and How to Avoid Them

### Pitfall 1: Thinking @ServiceConnection Always Sets spring.datasource.url

Wrong abstraction layer. It supplies **JdbcConnectionDetails** and other supported connection details; Environment may leave property URLs unchanged.

### Pitfall 2: Thinking @DynamicPropertySource Is Only for Databases

It supports any property key, including **app.partner.base-url** or **app.service.grpc-port**.

### Pitfall 3: Omitting spring-boot-testcontainers

Spring Boot's `@ServiceConnection` requires that integration module. **spring-boot-starter-test** alone does not include it.

### Pitfall 4: Using GenericContainer Without Helping Factories Identify the Service

For a `@Bean` method returning `GenericContainer`, Boot does not know the image before bean creation. Use **@ServiceConnection(name = "redis")** where appropriate or use a specific container class.

### Pitfall 5: Hardcoding Host Ports

Containers get dynamic mapped ports. Use **getJdbcUrl()**, **getHost()**, **getMappedPort()**, or ConnectionDetails.

### Pitfall 6: Non-Static @DynamicPropertySource Method

Spring TestContext requires a static method with one DynamicPropertyRegistry argument.

### Pitfall 7: Registering Both ConnectionDetails and Properties for the Same Service Unintentionally

Two competing paths obscure precedence and confuse debugging of which values consumers actually use.

### Pitfall 8: Testing Only contextLoads

Run a real JDBC query or client check to prove the app connects to the container.

### Pitfall 9: Losing Track of Context Caching

A cached context can hold a DataSource pointing to a stopped container. Coordinate lifecycles and isolation, using `@DirtiesContext` only when truly needed.

### Pitfall 10: Using @ServiceConnection for app.custom.key

Without a matching factory and consumer, the annotation cannot populate arbitrary keys. Use `@DynamicPropertySource` for custom keys.

### Pitfall 11: Missing Test Slice Configuration

With **@DataJpaTest**, consider **@AutoConfigureTestDatabase(replace = NONE)** when ensuring Testcontainers is not swapped for an embedded database.

### Pitfall 12: Container Tests Still Pointing to Production

A serious risk. Isolate tests completely from production endpoints and credentials; never fall back to production defaults when building a test DataSource.

### Pitfall 13: Stopping Containers at the Wrong Time

If a container stops while a Spring context still holds an open connection pool, connection timeout errors occur. Choose clear lifecycles and avoid stopping containers inside arbitrary test methods.

### Pitfall 14: Failing to Verify Docker Runtime Availability

Without a running daemon or compatible runtime, Testcontainers cannot start services. Configure CI execution environments properly.

### Pitfall 15: Assuming All ConnectionDetails Factories Exist in Every Version

Spring Boot adds factories across releases. For 3.3, consult the 3.3 factory list rather than blindly applying examples from newer versions.

### Pitfall 16: Treating Testcontainers Credentials as Production Secrets

Container credentials in tests are dummy test data. Never expose real passwords in Java source or CI logs.

## 30. Practice Exercises

### Exercise A — Configuring PostgreSQL with DynamicPropertySource

1. Add JDBC, PostgreSQL driver, Testcontainers, and starter-test dependencies.
2. Declare a static PostgreSQLContainer.
3. Annotate with **@Testcontainers** and **@Container**.
4. Write a **static @DynamicPropertySource** method.
5. Register URL, username, and password with **registry.add**.
6. Inject JdbcTemplate and execute `SELECT 1`.
7. Log **non-sensitive** JDBC URL or database name in the test to observe the dynamic mapped port.

**Expected result:** DataSource connects to the real container, not the local DB.

### Exercise B — Migrating to ServiceConnection

1. Keep the static PostgreSQLContainer.
2. Delete the **@DynamicPropertySource** method.
3. Add **@ServiceConnection** to the container field.
4. Ensure **spring-boot-testcontainers** is on the test classpath.
5. Re-run `SELECT 1`.
6. Compare line count and connection mechanics.

**Expected result:** auto-configuration consumes the container's JdbcConnectionDetails.

### Exercise C — Comparing Properties in Environment

1. Put a dummy JDBC URL in `application-test.yml`.
2. Run a ServiceConnection test querying the PostgreSQL container.
3. Read **Environment.getProperty("spring.datasource.url")**.
4. Compare with the real URL from **DataSource.getConnection().getMetaData().getURL()**.

**Expected result:** clearly observe that Environment properties do not necessarily reflect active ConnectionDetails.

### Exercise D — Custom HTTP Endpoint

1. Create a GenericContainer exposing an HTTP port.
2. Create **PartnerProperties(baseUrl)** under prefix **app.partner**.
3. Use DynamicPropertyRegistry to supply base URL via getHost/getMappedPort.
4. Bind PartnerProperties.
5. Assert baseUrl matches the dynamic endpoint.

**Expected result:** DynamicPropertySource handles custom settings without needing a ServiceConnection factory.

### Exercise E — Redis with GenericContainer

1. Add matching Redis starter/client dependencies for tests.
2. Create a Redis GenericContainer exposing 6379.
3. Add **@ServiceConnection(name = "redis")** on the container or `@Bean`.
4. Assert the Redis client runs a simple command against the container.
5. Remove `name` on the GenericContainer `@Bean` case and observe how factory matching changes.

**Expected result:** understand how ServiceConnection factories match by class, image, and name.

### Exercise F — Container as a Spring Bean

1. Create a **@TestConfiguration** with a **@Bean @ServiceConnection** returning PostgreSQLContainer.
2. **@Import** it into `@SpringBootTest`.
3. Omit JUnit `@Container` for this bean.
4. Execute `SELECT 1`.
5. Inspect its lifecycle relative to Spring TestContext caching.

**Expected result:** distinguish JUnit-managed containers from Spring-managed containers.

### Exercise G — Checking Test Slice Replacement

1. Create a JPA repository test with `@DataJpaTest`.
2. Attach PostgreSQLContainer and ServiceConnection.
3. Add **@AutoConfigureTestDatabase(replace = NONE)** as needed.
4. Run a PostgreSQL-specific query.
5. Verify the test was not switched to an embedded DB.

**Expected result:** tests run against a backend closely matching production.

### Exercise H — Combining Both Mechanisms

1. Use `@ServiceConnection` for PostgreSQL.
2. Use `@DynamicPropertySource` for a custom HTTP mock URL.
3. Assert both the JDBC query and PartnerProperties.
4. Do not call `registry.add` for JDBC keys already handled by ServiceConnection.
5. Document clear ownership boundaries per container.

**Expected result:** both annotations complement each other cleanly in one integration test.

## 31. Decision Checklist

Answer these questions when choosing:

- Does your service have a Spring Boot ConnectionDetails factory?
- Does your app use auto-configuration that reads ConnectionDetails?
- Do you need **spring.datasource.*** or an **app.custom.*** key?
- Should the test manage individual properties explicitly or let Boot infer the connection?
- Are there multiple containers of the same type?
- Is the container a JUnit static field or a Spring `@Bean`?
- If a `@Bean` returns GenericContainer, is a `name` hint needed?
- Is **spring-boot-testcontainers** included when using ServiceConnection?
- If using `@DynamicPropertySource`, is the method static with a valid Supplier?
- Is a compatible Docker runtime verified in CI?
- Are fixed host ports avoided?
- Does a real query/IO test verify actual connectivity?
- Are context caching and lifecycles aligned?
- Is a test slice silently swapping in an embedded database?
- Are you mistakenly checking `Environment.getProperty` to verify ConnectionDetails?
- Are real credentials kept out of test sources and logs?
- Is `@DirtiesContext` used only when needed rather than slowing runs needlessly?
- Did you check the factory list for your exact Spring Boot version?

## 32. Summary

- **@DynamicPropertySource** is a **Spring Framework TestContext** API that adds dynamic properties into Spring Environment via **DynamicPropertyRegistry** and **Supplier**.
- **@ServiceConnection** is a **Spring Boot Testcontainers** integration that creates **ConnectionDetails** beans from containers for compatible auto-configurations.
- For PostgreSQL JDBC, ServiceConnection provides **JdbcConnectionDetails** and eliminates manual URL, username, and password registration.
- **ConnectionDetails takes priority over connection-related configuration properties** in supporting consumers; it does not overwrite Environment keys.
- **@DynamicPropertySource** works flexibly for any key, especially **app.partner.base-url** or custom service endpoints.
- **@ServiceConnection** requires **spring-boot-testcontainers**; not every container or custom image has a factory.
- For a **GenericContainer @Bean**, **@ServiceConnection(name = "redis")** may be needed so Spring Boot identifies the service.
- **@Testcontainers** and **@Container** manage JUnit container lifecycles; `@ServiceConnection` does not do that.
- **@Bean** containers managed by Spring Boot follow the test ApplicationContext lifecycle.
- Both mechanisms can be **combined** in one test when each handles a distinct connection.
- Tests should verify **clients actually use the container**, not only that the context starts or Environment holds a string.
- Context caching, test slices, mapped ports, and Docker runtimes determine how reliable integration tests are.

## Official Documentation References

- Spring Boot 3.3 — Testcontainers, *Service Connections*, *Dynamic Properties*, *Using Spring Beans*: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — Spring Boot Testcontainers module and ServiceConnection API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/testcontainers/service/connection/ServiceConnection.html
- Spring Framework 6.1 — DynamicPropertySource API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/DynamicPropertySource.html
- Spring Framework — Context Configuration with Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Testcontainers Java — JUnit 5 Quickstart: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
