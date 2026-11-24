# Distinguishing Spring Framework Configuration from Spring Boot Auto-Configuration for DataSource

## 1. Both Use Spring JDBC, Yet Who Creates the DataSource?

In a Java database application, `DataSource` (from JDBC's `javax.sql.DataSource`) is the contract providing `Connection`s. `JdbcTemplate` uses `DataSource` to execute SQL; the transaction manager uses the matching connection source to coordinate commit/rollback. Every application must have a properly configured connection source, whether declared directly by the developer or auto-configured by Spring Boot based on classpath and properties.

**Plain Spring Framework** provides the IoC container, dependency injection, JDBC/transaction APIs, and bean declaration mechanisms. It does not automatically create a `DataSource` merely because the project has the `spring-jdbc` library or an `application.properties` file. You normally must register the needed beans, declare properties, and choose implementations via code/XML or explicit configuration.

**Spring Boot** builds on Spring Framework, adding **auto-configuration**: when matching conditions hold, Boot pre-creates common beans such as `DataSource`, `JdbcTemplate`, `NamedParameterJdbcTemplate`, and the transaction manager. Values can be derived from properties such as `spring.datasource.url`, `spring.datasource.username`, or database drivers on the classpath. If the application already supplies a given bean itself, the corresponding auto-configuration typically yields to that bean per each auto-configuration's conditions.

In short:

- **Spring Framework:** "I provide the container and APIs; you declare which components need to exist."
- **Spring Boot:** "I use the Spring container and try declaring sensible configuration from dependencies, properties, and existing beans; you can still customize."

Auto-configuration **is not** a new JDBC API, **does not eliminate** `DataSource`, and **does not replace** understanding connections, pooling, transactions, or DB constraints.

## 2. Runtime Dependency Chain

```text
                        Application
                           |
                           v
                     Repository/DAO
                           |
                           v
                      JdbcTemplate
                           |
                           v
                    javax.sql.DataSource
                           |
                  acquire / return Connection
                           |
                           v
                  JDBC driver / database

    Spring-managed transaction (if configured)
                    |
                    v
            PlatformTransactionManager
                    |
                    v
                 DataSource
```

The difference between Framework and Boot lies mainly in **how beans are constructed** and **where configuration values come from**, not in the SQL operations executed by `JdbcTemplate`. The same `JdbcTemplate` still uses `DataSourceUtils` to participate in a Spring-managed connection when an appropriate transaction exists.

### 2.1. Role of Each Component

| Component | What Does Spring Framework Provide? | What Does Spring Boot Add? |
| --- | --- | --- |
| `DataSource` | Uses JDBC interface; allows registering an implementation as a bean | Can auto-create bean from dependencies, connection info, and auto-config conditions |
| `DriverManagerDataSource` | Simple implementation in `spring-jdbc`, creates new connection when requested | Not Boot's default pool |
| HikariCP | Can be manually declared/chosen when library is present | Typically chosen by Boot as JDBC pool when HikariCP is on classpath and not replaced by another choice |
| `JdbcTemplate` | Provides classes and SQL, mapper, callback APIs | Can auto-create `JdbcTemplate` bean when conditions are met |
| `NamedParameterJdbcTemplate` | Provides `:name` parameter API | Can auto-create matching bean when conditions are met |
| `PlatformTransactionManager` | Provides abstraction and implementations such as `JdbcTransactionManager` | Can auto-create JDBC transaction manager if a suitable `DataSource` exists and is not overridden |
| `@Transactional` | Defines metadata and Spring transaction infrastructure, must be enabled/configured | Auto-config helps set up many transaction components when conditions hold, though proxy/transaction rules still apply |
| JDBC driver | Driver sits in runtime dependencies | Driver must still be on classpath; Boot can infer driver class name from common JDBC URLs |
| URL, user, password | You decide how to supply/bind | Boot provides binder and common `spring.datasource.*` properties |

`DataSource` is not necessarily a pool. For example, `DriverManagerDataSource` is convenient for lessons/tests, yet **has no connection pooling**. In production applications, consider a pool that manages connection limits, timeouts, health checks, and lifecycle.

## 3. Plain Spring Framework: Declaring Beans Manually

### 3.1. Decisions That Must Be Made Explicit

With an application using Spring Framework directly, you typically need to:

1. Add `spring-context`, `spring-jdbc`, and database driver dependencies.
2. Choose a `DataSource` implementation; provide URL, user, password, and pool parameters if any.
3. Declare the `DataSource` bean using `@Configuration`/`@Bean` (or XML).
4. Declare `JdbcTemplate`, passing in `DataSource`.
5. If transactions are needed, declare a matching `PlatformTransactionManager`, enable transaction infrastructure (e.g., `@EnableTransactionManagement`), and place `@Transactional` boundaries appropriately.
6. Choose and manage how properties are read from files, environment, or secret stores; Spring Framework does not automatically understand `spring.datasource.url` as a Spring Boot convention.

You can write `new JdbcTemplate(dataSource)` directly, though letting services/repositories use dependency injection keeps bean management clearer and easier to test.

### 3.2. Complete Program: Spring Framework + H2

Example using **Java 17+**, **Spring Framework 6.2.12**, and H2. The program runs without Spring Boot and without installing a database server. Note that versions here are **pinned for illustration**, not meant to indicate the latest releases.

Structure:

```text
framework-datasource-demo/
├── pom.xml
└── src/main/java/example/FrameworkDataSourceDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>framework-datasource-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/FrameworkDataSourceDemo.java`:

```java
package example;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

public class FrameworkDataSourceDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class JdbcConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource source = new DriverManagerDataSource();
            source.setDriverClassName("org.h2.Driver");
            source.setUrl("jdbc:h2:mem:frameworkdemo;DB_CLOSE_DELAY=-1");
            source.setUsername("sa");
            source.setPassword("");
            return source;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(JdbcConfig.class)) {
            DataSource dataSource = context.getBean(DataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager transactionManager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("CREATE TABLE people (id BIGINT PRIMARY KEY, name VARCHAR(80))");
            jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Lan");
            String name = jdbc.queryForObject(
                    "SELECT name FROM people WHERE id = ?",
                    String.class, 1L);

            System.out.println("Framework DataSource: "
                    + dataSource.getClass().getSimpleName());
            System.out.println("Framework JdbcTemplate: "
                    + jdbc.getClass().getSimpleName());
            System.out.println("Framework transaction manager: "
                    + transactionManager.getClass().getSimpleName());
            System.out.println("Framework query: " + name);
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.FrameworkDataSourceDemo
```

Output printed by the program (excluding Maven logs):

```text
Framework DataSource: DriverManagerDataSource
Framework JdbcTemplate: JdbcTemplate
Framework transaction manager: JdbcTransactionManager
Framework query: Lan
```

**Why does the example work?**

- `AnnotationConfigApplicationContext` loads `JdbcConfig` and recognizes three `@Bean` methods.
- `DataSource` is a bean **explicitly created** by the developer; Spring does not automatically choose H2, URL, or username.
- The container injects the exact same `DataSource` into `JdbcTemplate` and `JdbcTransactionManager`.
- `JdbcTemplate` executes table creation, insert, and select via JDBC; `DB_CLOSE_DELAY=-1` keeps the in-memory database alive across different connections within the same process.
- `DriverManagerDataSource` does not reuse connections via a pool; use it only for illustrations or simple cases, do not take this configuration verbatim to production.

`@EnableTransactionManagement` allows Spring to apply `@Transactional` to eligible beans when calls go through a transaction proxy. The example does not declare a transactional service since each SQL operation is simple; declaring the transaction manager here highlights the Framework's configuration responsibilities.

If you remove the `@Bean JdbcTemplate` method, `context.getBean(JdbcTemplate.class)` will fail because **plain Spring Framework does not create JdbcTemplate automatically**. If you remove `DataSource`, the container also has no connection source to inject into dependent beans.

## 4. Spring Boot: Auto-Configuration When Conditions Hold

Spring Boot uses `@SpringBootApplication`, which includes enabling auto-configuration alongside application configuration and component scanning. When JDBC libraries, pool/embedded DB, and appropriate beans are present, auto-configuration classes activate conditionally.

In common JDBC usage, the conceptual chain is:

```text
Dependencies + application.properties/yaml + existing beans
                         |
                         v
                  Spring Boot auto-config
                         |
            check classpath / conditions
                         |
         +---------------+---------------+
         |                               |
 App-defined DataSource exists?      No DataSource yet?
         |                               |
 Use declared bean;                  Boot tries creating bean if
 some auto-config backs off          matching conditions hold
         |                               |
         +---------------+---------------+
                         |
                         v
                 DataSource candidate
                         |
         +---------------+---------------+
         |                               |
  JdbcTemplate bean?            Transaction manager bean?
  (if conditions hold)          (if conditions hold)
```

Boot uses configurations such as `DataSourceAutoConfiguration`, `JdbcTemplateAutoConfiguration`, and transaction-related configurations. Class names, packages, and condition details may vary across Boot version lines; **the core mechanism is conditions on classpath, properties, and existing beans**.

Cases to understand:

- Having `spring-boot-starter-jdbc`, HikariCP (pulled in by the starter), and a matching JDBC driver: Boot can usually create a pooled `DataSource`.
- Having embedded H2/HSQLDB/Derby on the classpath: Boot may configure an embedded database when no URL is supplied, depending on context and version.
- Having only `spring.datasource.url` in a file while missing the required DataSource/driver dependencies: connectivity cannot be established; a property does not turn into a JDBC driver.
- Having an application-defined `@Bean DataSource`: default `DataSource`-creating auto-configuration typically **backs off**; other auto-configs can still create templates/transaction managers based on that bean.
- Having two `DataSource`s without designating a candidate: autowiring by type can be ambiguous; `JdbcTemplate` auto-configuration requires an appropriate candidate.
- A project using only R2DBC/reactive has a different reactive connection configuration: do not infer a JDBC `DataSource` will be created. R2DBC is not JDBC.

### 4.1. Common Spring Boot Properties

```properties
# PostgreSQL example, requires PostgreSQL JDBC driver dependency:
spring.datasource.url=jdbc:postgresql://localhost:5432/sales
spring.datasource.username=app_user
spring.datasource.password=change-me

# Boot typically selects HikariCP when Hikari is on the classpath:
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
```

This is a **configuration example**, not real secrets. In practice, supply passwords via environment variables/a secret manager rather than committing them to repositories.

| Property Group | Meaning |
| --- | --- |
| `spring.datasource.url` | Connection JDBC URL; omitting it requires another inference source such as an embedded DB |
| `spring.datasource.username` / `password` | Connection credentials; should be supplied via secure environment configuration |
| `spring.datasource.driver-class-name` | Driver class; usually inferred from common URLs if the driver JAR is available |
| `spring.datasource.type` | Can specify a DataSource implementation instead of the default choice |
| `spring.datasource.hikari.*` | Tunes the Hikari pool when the actual DataSource uses Hikari |
| `spring.sql.init.*` | Configures running schema/data SQL scripts at startup, separate from connection config |
| `spring.jpa.*` | Configures JPA/Hibernate if the app uses JPA; not required for JdbcTemplate |

Each property group is processed by a specific mechanism. Specifically, **`spring.datasource.hikari.maximum-pool-size` does not turn `DriverManagerDataSource` into a connection pool** if you manually registered `DriverManagerDataSource` and Boot did not create Hikari.

### 4.2. Complete Program: Spring Boot + H2

The second example uses **Java 17+**, **Spring Boot 3.5.7**, and the JDBC starter. The version is pinned so learners can reproduce the example, not to claim this is the latest Boot release.

Structure:

```text
boot-datasource-demo/
├── pom.xml
└── src/main/
    ├── java/example/BootDataSourceDemo.java
    └── resources/application.properties
```

`pom.xml`:

```xml
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
    <artifactId>boot-datasource-demo</artifactId>
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
            <scope>runtime</scope>
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
```

`src/main/resources/application.properties`:

```properties
spring.main.banner-mode=off
logging.level.root=ERROR

spring.datasource.url=jdbc:h2:mem:bootdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
```

`src/main/java/example/BootDataSourceDemo.java`:

```java
package example;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class BootDataSourceDemo {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(BootDataSourceDemo.class, args)) {
            // CommandLineRunner runs once the context is ready.
        }
    }

    @Bean
    CommandLineRunner inspectDataSource(
            DataSource dataSource, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute("CREATE TABLE people (id BIGINT PRIMARY KEY, name VARCHAR(80))");
            jdbc.update(
                    "INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Lan");
            String name = jdbc.queryForObject(
                    "SELECT name FROM people WHERE id = ?", String.class, 1L);

            System.out.println("Boot DataSource: "
                    + dataSource.getClass().getSimpleName());
            System.out.println("Boot JdbcTemplate: "
                    + jdbc.getClass().getSimpleName());
            System.out.println("Boot query: " + name);
        };
    }
}
```

Run in the `boot-datasource-demo` directory:

```bash
mvn -q spring-boot:run
```

With the classpath/starter and configuration above, the lines printed by the program are:

```text
Boot DataSource: HikariDataSource
Boot JdbcTemplate: JdbcTemplate
Boot query: Lan
```

**What differs from the plain Framework example?**

- The code does not declare `@Bean DataSource`, `@Bean JdbcTemplate`, or a transaction manager itself. Boot auto-configures these thanks to the starter, H2, properties, and absence of competing beans.
- `spring-boot-starter-jdbc` supplies Spring JDBC along with related components, typically including HikariCP; the H2 driver is declared separately.
- URL/user/password from `application.properties` are fed by Boot into `DataSource` creation; the Hikari pool receives `maximum-pool-size=5`.
- `CommandLineRunner` is created as an application bean; Boot injects the auto-configured beans into its method parameters.
- Repository/SQL code can be completely identical to plain Framework: `JdbcTemplate` continues executing standard SQL and JDBC mapping.

Startup logs, driver versions, and Maven message formatting may vary by environment. The output above is the **`System.out.println` lines**, not a full console capture.

### 4.3. Why Should Boot Not Be Treated as Magic?

In the Boot example, the prerequisites were already prepared:

1. The starter is present to enable the right auto-configurations.
2. The H2 driver is on the runtime classpath.
3. A valid JDBC URL is provided.
4. No custom `DataSource` bean is registered that would cause defaults to back off.
5. One clear `DataSource` exists for auto-config to create `JdbcTemplate`.

If any condition is missing, startup can fail, beans may not exist, or the deployment behaves differently. For instance, simply adding `spring.datasource.url=jdbc:postgresql:...` without declaring the PostgreSQL JDBC driver prevents Boot from creating a working PostgreSQL connection.

## 5. Direct Responsibility Comparison

| Question | Plain Spring Framework | Spring Boot |
| --- | --- | --- |
| Who decides to create `DataSource`? | Developer/configuration provided by the project | Auto-config if conditions hold, or user-defined bean |
| Who supplies URL and credentials? | Project-designed Java config/XML/property binding | `spring.datasource.*` and Externalized Configuration if auto-config applies |
| Is `JdbcTemplate` created out of the box? | Not automatically just from having the JAR | Conditionally created when a suitable DataSource exists |
| Is there a default pool? | No default pool policy; you choose | HikariCP is typically prioritized when the classpath fits |
| Who manages transactions? | You register the manager and enable infrastructure as needed | Boot can auto-configure an appropriate manager; you still decide `@Transactional` boundaries |
| Are SQL and mapping still needed? | Yes | Yes |
| Can both use the same Spring JDBC library? | Yes | Yes; Boot uses the Framework libraries underneath |
| Do user-defined beans take precedence? | You define the beans yourself | Related auto-config typically backs off when a suitable user bean exists |
| Is it easy to see directly which beans exist? | Mostly declared transparently in config | Need to check the condition report and runtime bean list |
| Can it be used in production? | Yes, if you configure pooling, timeouts, transactions, secrets, and observability yourself | Yes, if you control autoconfig/properties, pool, timeouts, transactions, secrets, and observability |

Do not think "plain Framework = old" and "Boot = new". Boot uses Spring Framework itself, and a Boot app can still contain many custom `@Configuration` classes. **The choice is the level of default configuration and wiring mechanism**, not two different DB access technologies.

## 6. When Manually Declaring DataSource in a Spring Boot Application

### 6.1. Boot Backs Off, Yet Only for Related Parts

Suppose a Boot app has this bean:

```java
// Illustrative snippet inside a Spring Boot app that already has spring-jdbc dependency.
@Configuration(proxyBeanMethods = false)
class CustomJdbcConfiguration {
    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:custom;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }
}
```

This snippet requires importing `@Configuration`, `@Bean`, `DataSource`, `DriverManagerDataSource`, and the H2 driver as in earlier examples. This is an **illustrative snippet**, not a standalone runnable file.

Once this `DataSource` bean is present, the part of Boot that creates a default `DataSource` usually stops running. Yet auto-config for `JdbcTemplate` can still use that bean; it does not mean "declaring one bean turns off all of Boot's auto-configuration".

Specifically:

- `spring.datasource.url` in `application.properties` does not necessarily apply to the `DriverManagerDataSource` you `new`-ed above. Your custom bean uses the values set inside your method.
- `spring.datasource.hikari.maximum-pool-size` has no effect on a `DriverManagerDataSource` bean; it is not Hikari.
- If your custom bean is a pooled `HikariDataSource`, which properties get bound depends on how you declare `@ConfigurationProperties` or use `DataSourceProperties`/builders—there is no rule that "every custom bean automatically receives all `spring.datasource.*`".
- You can override the `JdbcTemplate` bean for custom needs; Spring Boot then creates the default only when missing-bean conditions hold. Avoid defining two beans with the same name without controlling conflict behavior.

### 6.2. Using Spring Boot While Still Declaring Explicitly

A valid design is letting Boot manage startup, configuration/environment, and DI while manually creating the needed `DataSource`s. When multiple data sources exist, register each `DataSource`, `JdbcTemplate`, and transaction manager explicitly, using `@Qualifier` and occasionally `@Primary` to select candidates.

Conceptual example (not a complete Java file):

```java
@Bean
JdbcTemplate billingJdbc(
        @Qualifier("billingDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}

@Bean
JdbcTemplate reportingJdbc(
        @Qualifier("reportingDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

With two `JdbcTemplate` beans, unqualified `JdbcTemplate` injection also becomes ambiguous; name them and apply `@Qualifier` or `@Primary` for the right consumers. When business logic needs transactions, the transaction manager must bind to the right data source rather than picking an arbitrary bean.

With multiple DataSources, Boot cannot guess on its own which business logic uses which DB, which SQL must commit together, or whether distributed transactions are required.

## 7. Properties: Commonly Misunderstood Differences

### 7.1. Spring Framework Does Not Auto-Bind `spring.datasource.*`

In plain Framework, adding a file:

```properties
spring.datasource.url=jdbc:h2:mem:demo
spring.datasource.username=sa
spring.datasource.password=
```

is **not enough** to create a `DataSource` bean. You must load values and create the bean—for instance via `@PropertySource`/`Environment`, `@Value`, or a binder you explicitly invoke. Key names prefixed with `spring.datasource` carry special meaning only inside Boot's corresponding auto-configurations/binders.

An illustrative example in plain Framework:

```java
@Configuration
@PropertySource("classpath:jdbc.properties")
class DataSourceConfiguration {
    @Bean
    DataSource dataSource(Environment env) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl(env.getRequiredProperty("db.url"));
        ds.setUsername(env.getRequiredProperty("db.user"));
        ds.setPassword(env.getRequiredProperty("db.password"));
        return ds;
    }
}
```

The snippet needs the corresponding Spring imports and bean context; `src/main/resources/jdbc.properties` must contain `db.url`, `db.user`, and `db.password`. This illustrates the **property-loading mechanism**, not a mandatory configuration for every Framework project. In production environments, avoid storing real passwords in source.

### 7.2. Boot Externalized Configuration Does Not Replace Choosing a Database

Boot supports `application.properties`, `application.yml`, runtime environment, command-line arguments, profiles, and other property sources. This is convenient for deployment, yet does not create drivers or databases by itself.

Profile-separated configuration example:

```properties
# application-dev.properties
spring.datasource.url=jdbc:h2:mem:devdb
spring.datasource.username=sa
spring.datasource.password=
```

```properties
# application-prod.properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/appdb
spring.datasource.username=app_user
spring.datasource.password=use-runtime-secret
```

In practice, production passwords should be secrets injected at runtime; never commit real values. Select profiles via environment/CLI, e.g., `--spring.profiles.active=dev`. Do not mix `dev` and `prod` profiles in a way that causes two URLs to compete unintentionally.

**Note:** test mode using H2 can miss differences in dialect, constraints, isolation, and indexing of production DBs. Auto-configuration does not guarantee substitute databases share identical behavior.

## 8. Schema Initialization and JPA: Other "Automatic" Features Easy to Conflate

Having a `DataSource` only means connections can be acquired. It **does not imply** tables already exist.

In plain Spring Framework, you decide yourself whether to run DDL via Flyway/Liquibase, SQL scripts with `ResourceDatabasePopulator`, or another migration tool. In Boot, SQL initialization can read `schema.sql` and `data.sql` per configuration. Across many Boot versions, default SQL init targets embedded databases; external databases may require `spring.sql.init.mode=always` if you genuinely want scripts to run, though production should normally prefer controlled migrations.

Do not equate three distinct things:

1. **DataSource auto-configuration:** creates the JDBC connection factory bean.
2. **SQL initialization:** optionally runs schema/data scripts.
3. **JPA/Hibernate DDL:** behavior specific to JPA and `spring.jpa.hibernate.ddl-auto` properties, not `JdbcTemplate` itself.

A Boot JDBC app using `JdbcTemplate` without JPA **needs no entities, Hibernate, or JPA repositories**. Adding the JPA starter can introduce different auto-configs and transaction policies; inspect actual beans rather than assuming every Boot JDBC app runs Hibernate.

In the example programs above, `CREATE TABLE` was called explicitly to avoid depending on schema initialization mechanics.

## 9. Transactions: Not Just Adding an Annotation

`@Transactional` is a Spring Framework annotation, not exclusive to Spring Boot. In plain Framework, you typically configure a `PlatformTransactionManager` and enable transaction management; Boot can create the matching bean when conditions hold. **Both approaches require a transaction manager matching the DataSource that the repository uses.**

Illustrative service example:

```java
@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        int deducted = jdbc.update(
                "UPDATE account SET balance = balance - ? " +
                "WHERE id = ? AND balance >= ?",
                amount, fromId, amount);
        if (deducted != 1) {
            throw new IllegalStateException("Insufficient funds");
        }

        int added = jdbc.update(
                "UPDATE account SET balance = balance + ? WHERE id = ?",
                amount, toId);
        if (added != 1) {
            throw new IllegalStateException("Destination not found");
        }
    }
}
```

This is an **illustrative snippet**, not a standalone runnable program: it requires imports for `JdbcTemplate`, `@Service`, `@Transactional`, an `account` table, bean configuration, and a transaction manager. Production needs checks for positive amounts, non-identical accounts, numeric types, concurrency, and appropriate isolation.

Why do transactions relate to DataSource?

- `JdbcTransactionManager`/`DataSourceTransactionManager` binds a transaction to a connection obtained from a single `DataSource`.
- `JdbcTemplate` obtains connections cooperatively with Spring so statements inside a transaction can reuse the connection bound to that transaction.
- If an adapter explicitly opens a connection outside Spring's transaction mechanism, the statement may not join the transaction even when called from an annotated service.
- Using multiple distinct DataSources does not create an automatic distributed transaction. A local JDBC transaction manager manages its own resource and does not coordinate atomic commits across two independent databases.
- With default Spring proxies, self-invoking `this.transfer(...)` from the same class bypasses advice; calls must go through the appropriate proxy.
- Default rollback applies to `RuntimeException` and `Error`, not checked exceptions unless configured. Catching and "swallowing" an error can make Spring treat the method as successful.

Therefore, do not view `@Transactional` as sufficient proof that "all SQL statements in the application share one transaction". In both Framework and Boot, rollback paths must be verified with integration tests.

## 10. How to Discover Which Beans Boot Created

Auto-configuration runs conditionally, so **verify actual behavior** instead of guessing.

### 10.1. Runtime Investigation

You can temporarily print bean types:

```java
@Bean
CommandLineRunner inspect(
        DataSource source, JdbcTemplate jdbc) {
    return args -> {
        System.out.println(source.getClass().getName());
        System.out.println(jdbc.getClass().getName());
    };
}
```

This illustrative snippet requires importing `@Bean`, `CommandLineRunner`, `DataSource`, `JdbcTemplate`, and a Boot application. If injection fails due to missing or ambiguous beans, the startup error itself is the clue to investigate.

Boot supports enabling the condition evaluation report via `--debug` or `debug=true` for eligible apps, showing why an auto-configuration applied or did not apply. With Spring Boot Actuator installed and the matching endpoint exposed, `/actuator/conditions` also reveals conditions; endpoints must be exposed and secured carefully, never left public in production.

Check these questions:

1. Which dependencies exist at runtime (Spring JDBC, pool, driver, JPA/R2DBC)?
2. Which `DataSource` bean actually exists, and what is its type? Are there multiple beans?
3. Which properties are loaded from profiles/env/CLI? What is the actual final URL?
4. For what condition did Boot skip `DataSourceAutoConfiguration` or `JdbcTemplateAutoConfiguration`?
5. Which transaction manager exists and which DataSource does it manage?
6. Does the pool have appropriate connection limits, timeouts, and leak detection?

Do not print passwords, tokens, or JDBC URLs with embedded credentials into logs. Enabling debug in production must weigh what configuration info could be exposed.

### 10.2. Typical Failure Scenarios

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| Plain Framework reports `DataSource` bean not found | `@Bean` not registered / wrong config scan | Verify `@Configuration` is loaded; create the appropriate bean |
| Plain Framework missing `JdbcTemplate` | DataSource exists, yet template bean not created | Declare `new JdbcTemplate(dataSource)` under `@Bean` |
| Boot reports unable to determine DataSource | Missing JDBC URL, no embedded DB, missing driver or required starter | Check dependencies, properties, actual database |
| Has `spring.datasource.url` yet uses a different URL | Custom code-created DataSource or another config/profile overriding | Inspect actual bean and active property source |
| `spring.datasource.hikari.*` has no effect | Actual bean is not Hikari or is not bound | Inspect `dataSource.getClass()` and binding mechanism |
| Injecting `DataSource` reports multiple candidates | Multiple beans implementing the same interface | Use `@Primary`, `@Qualifier`, or redesign bean wiring |
| Boot has DataSource yet lacks template auto-config | Missing Spring JDBC, multiple candidates, or another matching bean | Inspect condition report and declare bean manually if needed |
| Has template yet SQL fails "table not found" | Connection succeeded, yet schema not initialized | Use proper migrations/SQL initialization |
| `@Transactional` does not roll back | Missing right proxy/manager, self-invocation, wrong DataSource, or swallowed exception | Inspect context, manager bean, call path, and integration tests |
| High requests exhaust connections | Pool limit, connection leaks, slow queries/transactions | Measure pool metrics, query latency, timeouts, and transaction length |

Some failures can occur in both models because they reside in the DB/driver rather than auto-configuration: wrong credentials, dropped network, deadlocks, slow queries, wrong schema tables, or insufficient DB user privileges.

## 11. Testing Configuration and Production Choices

**Plain Framework:** write tests creating `ApplicationContext`, assert the expected `DataSource`, `JdbcTemplate`, and transaction manager exist, test a real operation, and verify context/pool cleanup on close.

**Spring Boot:** use `@SpringBootTest` when testing full wiring, or `@JdbcTest` for a JDBC-focused test slice when appropriate. Test slices may replace DataSource with an embedded test database depending on configuration. If the goal is verifying exact PostgreSQL/MySQL connectivity and migrations, identify DB-replacement behavior and use a real database or Testcontainers.

Tests useful under either approach:

- Run simple SELECT/INSERT after startup against a clear test schema.
- Verify duplicate keys and exception translation.
- Verify two statements inside a transaction roll back together when the second fails.
- Verify `dev`/`test`/`prod` profiles use the right URL/driver, never accidentally using H2 in deployment.
- Verify the connection pool has sensible maximum size, connection timeout, and close lifecycle.
- With multiple DataSources, verify each `JdbcTemplate` and transaction manager points to the right source and bean selection is unambiguous.

**Production recommendations:** use a suitable connection pool, runtime-injected secrets, connection limits sized to DB capacity, timeouts, metrics, versioned migrations, rollback tests, and error handling. Boot reduces routine wiring boilerplate yet **cannot pick the right parameters for every load and every database automatically**.

## 12. Which Approach to Choose When Building an Application?

You can decide based on context:

- **Typical Spring Boot app, single JDBC database:** start with `spring-boot-starter-jdbc`, driver, and `spring.datasource.*`; leverage auto-configuration. Declare custom beans only when clearly needed.
- **Spring Framework app without Boot:** explicitly register `DataSource`, templates, transaction manager, and property loading; choose a pool suited to the environment.
- **Boot app with multiple DBs, datasource routing, custom pools, JNDI, or XA:** use explicit configuration per source, and verify exact auto-config conditions and transaction semantics.
- **Special environments with infrastructure policies:** you can keep Boot for DI/observability while manually managing part or all of datasource wiring.

Do not choose by line count of Java config. Weigh **operability**, transparency, multiple data sources, secret management, transaction needs, and testing requirements.

### Self-Check Questions

1. Why does merely having `spring-jdbc` in plain Spring Framework not make a `DataSource` bean appear?
2. Can Spring Boot create a `JdbcTemplate` from a user-declared `DataSource` bean? What conditions apply?
3. With a manually created `DriverManagerDataSource` bean, does `spring.datasource.hikari.maximum-pool-size` take effect?
4. Why does Spring Boot still need the JDBC driver at runtime even when `spring.datasource.url` is set?
5. When two DataSources exist, why must `JdbcTemplate` and the transaction manager be selected per source?
6. If a DataSource exists and a SELECT succeeds, is that enough to prove transaction rollback works?
7. How does `DataSourceAutoConfiguration` differ from SQL schema initialization and JPA DDL?
8. When a Boot app fails to auto-configure DataSource, in what order should you inspect classpath, properties, existing beans, and the condition report?

**Remember:** Spring Framework and Spring Boot use the same JDBC abstractions; the difference is **who declares, selects, and binds the infrastructure beans**. Plain Spring Framework requires explicit wiring. Spring Boot applies conditional defaults, backs off when the application defines suitable beans, and allows reconfiguration. Both still require properly managing the JDBC driver, DataSource, pool, SQL schema, and transactions.

### Official References

- Spring Framework — Data Access / JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc.html
- Spring Framework — Data Access / Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot — Working with SQL Databases: https://docs.spring.io/spring-boot/reference/data/sql.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
