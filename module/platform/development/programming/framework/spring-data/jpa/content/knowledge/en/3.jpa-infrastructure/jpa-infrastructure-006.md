# Role of JpaVendorAdapter and Provider Properties

## Objectives

After this lesson, you can:

- Explain where JpaVendorAdapter fits in the Spring Data JPA and Spring ORM architecture.
- Distinguish JpaVendorAdapter, JpaDialect, PersistenceProvider, and EntityManagerFactory.
- Configure HibernateJpaVendorAdapter in a Spring Framework application with manual JPA configuration.
- Use standard Jakarta Persistence properties as well as Hibernate- or other provider-specific properties.
- Configure JPA properties in Spring Boot using application.yml or application.properties.
- Diagnose cases where configuration is ignored, the wrong provider or dialect is selected, or unintended schemas are generated.

## 1. What Problem Does JpaVendorAdapter Solve?

JPA is a specification. Applications use APIs such as EntityManager, EntityManagerFactory, EntityTransaction, and mapping annotations to work with the persistence context. A JPA provider implements that specification. Hibernate ORM and EclipseLink are two examples of providers.

Spring ORM provides an integration layer to bring a JPA provider into Spring's lifecycle and transaction management mechanism. In configurations using LocalContainerEntityManagerFactoryBean, JpaVendorAdapter is the bridge between Spring and a specific provider.

A JpaVendorAdapter supplies vendor-dependent information and behavior, typically including:

- The PersistenceProvider that Spring will use to create the EntityManagerFactory.
- The corresponding JpaDialect so Spring can handle certain provider-specific transaction and exception behaviors.
- A map of default JPA/provider properties.
- Database platform information and configuration flags such as showing SQL or generating DDL, depending on the implementation.

In Spring ORM, common implementations include HibernateJpaVendorAdapter, EclipseLinkJpaVendorAdapter, and OpenJpaVendorAdapter. Choose the adapter matching the actual provider on the classpath and configured for the persistence unit.

### Position in the Architecture

The configuration flow can be visualized as follows:

~~~text
Spring Data JPA repositories
          |
          v
EntityManager / EntityManagerFactory
          ^
          |
LocalContainerEntityManagerFactoryBean
          |
          +---- JpaVendorAdapter
          |        +---- PersistenceProvider
          |        +---- JpaDialect
          |        +---- vendor defaults
          |
          +---- JPA properties
          |
          +---- DataSource
          |
          v
JPA provider (e.g., Hibernate)
          |
          v
JDBC driver
          |
          v
Database
~~~

Spring Data JPA repositories use EntityManager to perform persistence operations. EntityManagerFactory is created by the application's JPA configuration. JpaVendorAdapter participates when Spring initializes EntityManagerFactory; it is not a repository, not an EntityManager, and not a connection pool.

## 2. Distinguishing Related Components

| Component | Role | Example |
|---|---|---|
| JpaVendorAdapter | Supplies Spring ORM integration information for a JPA provider | HibernateJpaVendorAdapter |
| PersistenceProvider | Provider implementing EntityManagerFactory creation per the JPA standard | Hibernate, EclipseLink |
| JpaDialect | Bridges provider-specific behaviors with Spring transactions and exceptions | HibernateJpaDialect |
| LocalContainerEntityManagerFactoryBean | Spring FactoryBean to configure and initialize EntityManagerFactory | Sets DataSource, packagesToScan, adapter, and properties |
| EntityManagerFactory | Factory creating EntityManager instances for a persistence unit | Injected into the persistence layer |
| DataSource | Provides JDBC connections | HikariCP connecting to PostgreSQL |
| Spring Boot's JpaProperties | Collection of JPA settings bound by Spring Boot from application configuration | spring.jpa.show-sql |

JpaVendorAdapter does not replace JpaDialect. The adapter returns the dialect matching the provider so Spring ORM can coordinate transactions and certain JDBC operations. HibernateJpaVendorAdapter typically goes with HibernateJpaDialect.

The adapter also does not manage connection pools. DataSource and a pool like HikariCP are a separate configuration concern. Choosing an adapter does not automatically make a database compatible with the provider; the driver, dialect, schema, and library versions must still align.

## 3. HibernateJpaVendorAdapter

For Spring Data JPA applications using Hibernate, the commonly used implementation is:

~~~java
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;

HibernateJpaVendorAdapter adapter = new HibernateJpaVendorAdapter();
~~~

Common options:

- setShowSql(boolean): instructs the provider to display SQL statements via Hibernate's show SQL mechanism.
- setGenerateDdl(boolean): specifies whether the adapter should request DDL generation.
- setDatabasePlatform(String): specifies the database platform/dialect name when truly necessary.
- setDatabase(Database): selects the database type from Spring ORM's enum when the adapter needs to infer the platform.

Not every application needs to set all of these options. With modern Hibernate, the provider can usually recognize common databases from JDBC metadata. Therefore, do not hardcode a dialect out of habit without a specific requirement. When using an uncommon database or a custom dialect, verify the dialect matches the exact Hibernate major version.

setShowSql(true) is handy for quick experiments, though usually not the best way to manage logs in deployment environments. You can enable log categories to control SQL and bind values per environment. Bind values may contain sensitive data, so do not enable bind logging in production without proper protection procedures.

setGenerateDdl is an adapter integration flag; it is not a database migration tool. In real applications, manage schema changes with Flyway or Liquibase and configure Hibernate in validate or none mode depending on deployment workflows.

## 4. Configuring the Adapter in Spring Framework

When not using Spring Boot auto-configuration, an application can declare LocalContainerEntityManagerFactoryBean directly.

The example below uses Java 17+, Spring ORM, Spring Data JPA, Hibernate, and a DataSource configured elsewhere:

~~~java
package com.example.config;

import java.util.Properties;

import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(basePackages = "com.example.persistence")
public class JpaConfiguration {

    @Bean
    LocalContainerEntityManagerFactoryBean entityManagerFactory(
            DataSource dataSource) {

        HibernateJpaVendorAdapter adapter =
                new HibernateJpaVendorAdapter();

        adapter.setShowSql(false);
        adapter.setGenerateDdl(false);

        Properties properties = new Properties();
        properties.setProperty("hibernate.hbm2ddl.auto", "validate");
        properties.setProperty("hibernate.jdbc.time_zone", "UTC");
        properties.setProperty("hibernate.format_sql", "true");
        properties.setProperty("hibernate.jdbc.batch_size", "50");
        properties.setProperty("hibernate.order_inserts", "true");
        properties.setProperty("hibernate.order_updates", "true");

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.domain");
        factory.setPersistenceUnitName("application");
        factory.setJpaVendorAdapter(adapter);
        factory.setJpaProperties(properties);

        return factory;
    }

    @Bean
    PlatformTransactionManager transactionManager(
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

Points to understand:

1. DataSource is injected into the factory bean; this example does not create the pool or JDBC URL itself.
2. packagesToScan points to the packages containing entities to manage.
3. setJpaVendorAdapter selects Hibernate as the provider adapter.
4. setJpaProperties supplies additional properties understood by Hibernate.
5. JpaTransactionManager coordinates JPA transactions with Spring's transaction mechanism.
6. @EnableJpaRepositories specifies the package containing repository interfaces.

The Jakarta imports in this example fit the Spring Boot 3/Spring Framework 6 and JPA 3.1+ stack. If a project uses an older stack based on JPA 2.x, the API namespace may be javax.persistence; do not mix both namespaces in the same persistence stack.

In applications with multiple persistence units, each EntityManagerFactory needs its own configuration and its adapter must match that unit's provider. You must specify the entity package, repository package, transaction manager, and persistence unit name to prevent repositories from using the wrong factory.

## 5. Standard JPA Properties and Provider-Specific Properties

Not all configuration properties share the same level of portability.

### Standard Jakarta Persistence Properties

Properties in the jakarta.persistence namespace are defined by the Jakarta Persistence specification. They have standardized meaning across providers within the scope supported by the specification.

Examples you may encounter:

- jakarta.persistence.jdbc.driver
- jakarta.persistence.jdbc.url
- jakarta.persistence.jdbc.user
- jakarta.persistence.jdbc.password
- jakarta.persistence.schema-generation.database.action
- jakarta.persistence.validation.mode

In Spring applications, connection settings are typically placed on the DataSource rather than configuring JDBC directly in the JPA provider. When using Spring Boot, prefer spring.datasource.* for URL, user, and password.

### Hibernate-Specific Properties

Properties starting with hibernate. are Hibernate-specific configurations. They can enable features not standardized by JPA.

| Property | Effect | Notes |
|---|---|---|
| hibernate.hbm2ddl.auto | Controls Hibernate's schema generation/validation behavior | Does not replace versioned migrations |
| hibernate.show_sql | Prints SQL emitted by Hibernate | Can make logs hard to control |
| hibernate.format_sql | Formats SQL for readability | Useful in development environments |
| hibernate.jdbc.time_zone | Time zone used when Hibernate exchanges temporal values over JDBC | Commonly set to UTC and aligned with app/database |
| hibernate.jdbc.batch_size | Number of DML statements to group into a JDBC batch | Must verify driver and ID generation strategy |
| hibernate.order_inserts | Orders inserts to improve batch grouping | Can affect observed SQL ordering |
| hibernate.order_updates | Orders updates to improve batch grouping | Test behavior and performance |
| hibernate.default_batch_fetch_size | Default batch size for association fetching | This is read batching, different from JDBC DML batching |
| hibernate.generate_statistics | Enables Hibernate internal statistics | Used for diagnostics; evaluate overhead when enabled |

Valid property names and values depend on the Hibernate version. Before configuring, check the documentation for the exact major version in use.

### Other Provider-Specific Properties

EclipseLink uses its own namespace, such as eclipselink.logging.level, eclipselink.target-database, and eclipselink.ddl-generation. OpenJPA has its own properties like openjpa.Log and its JDBC options.

Do not pass hibernate.* properties to EclipseLink expecting them to take effect. A provider may ignore unrecognized properties or emit warnings depending on the version. When switching providers, review the entire property map, dialect, dependencies, and related persistence behaviors.

## 6. Configuring Properties in Spring Boot

In Spring Boot applications, there is normally no need to manually create HibernateJpaVendorAdapter. Auto-configuration selects the adapter based on the JPA provider on the classpath and application settings.

Use Spring Boot's top-level properties for common options:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/app
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

  jpa:
    show-sql: false
    hibernate:
      ddl-auto: validate
~~~

Hibernate-specific properties can be passed through spring.jpa.properties.*:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        jdbc:
          time_zone: UTC
          batch_size: 50
        order_inserts: true
        order_updates: true
        default_batch_fetch_size: 50
~~~

Spring Boot strips the spring.jpa.properties. prefix before passing properties to the JPA provider. The remaining key name must be spelled accurately and match what the provider expects; relaxed binding does not fix provider property names for you.

An equivalent application.properties can be used:

~~~properties
spring.jpa.show-sql=false
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.default_batch_fetch_size=50
~~~

Distinguish two configuration groups:

- spring.jpa.hibernate.ddl-auto is a convenience property provided by Spring Boot to control Hibernate's schema behavior.
- spring.jpa.properties.hibernate.* is the mechanism to forward provider-specific properties.

For DataSource configuration, prefer spring.datasource.*. Do not put the same connection details in both DataSource and the JPA property map without a clear reason, as that easily creates two conflicting sources of configuration.

### When Should You Manually Declare JpaVendorAdapter in Boot?

Only consider creating an adapter bean when low-level provider integration customization is needed or when configuring multiple persistence units. Before adding the bean, understand the auto-configuration conditions of your exact Spring Boot version because a custom bean can alter default beans and how Boot constructs EntityManagerFactory.

For simple applications, prefer spring.jpa.* and spring.jpa.properties.*. Only use manual adapter configuration when standard Boot properties cannot satisfy the requirement. After customizing, inspect startup logs and verify the right EntityManagerFactory, provider, and repositories are created.

## 7. Safe DDL and Migration Management

Hibernate supports common schema modes via hibernate.hbm2ddl.auto; Spring Boot provides spring.jpa.hibernate.ddl-auto for corresponding configuration.

| Value | High-Level Meaning | Common Use Case |
|---|---|---|
| none | Does not ask Hibernate to manage the schema | Schema is managed externally |
| validate | Verifies whether mappings are compatible with the current schema | Startup validation |
| update | Attempts to adjust the schema to match mappings | Mostly for prototyping; does not replace versioned migrations |
| create | Creates the schema on startup | Temporary environments |
| create-drop | Creates the schema on startup and drops it when EntityManagerFactory closes | Tests or disposable environments |

Detailed behavior can depend on the provider and version. Do not use update or create in production as a migration strategy. Schema changes should be reviewed, versioned, and deployed in a controlled order using Flyway or Liquibase. In production, validate or none is usually more appropriate depending on whether the application needs schema verification at startup.

## 8. Logging SQL and Query Parameters

There are two common ways to observe Hibernate's SQL:

1. Enable show SQL via the adapter or spring.jpa.show-sql.
2. Use the logging framework to enable Hibernate loggers.

Example log configuration for Hibernate 6 in application-dev.yml:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

org.hibernate.SQL logs SQL statements. org.hibernate.orm.jdbc.bind logs JDBC parameter bind values in Hibernate 6. Logger names can differ across major versions, so check the documentation for the version in use.

Use dev or test profiles for verbose configurations. Bind values can contain passwords, emails, personal information, or sensitive business data. Do not enable TRACE for bind parameters in production without assessing risk, log access permissions, and retention policies.

## 9. How to Verify Configuration Takes Effect

When a property does not work, inspect both application configuration and the actual dependencies/provider.

### Step 1: Check the Provider in the Dependency Graph

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.hibernate.orm:hibernate-core
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

Confirm the provider is the right version and there are no unexpected multiple providers on the classpath.

### Step 2: Check Spring Configuration

With Spring Boot, check active profiles and higher-precedence configuration sources such as environment variables, command-line arguments, or external config. An application-prod.yml can override values in application.yml.

With manual configuration, check that the right LocalContainerEntityManagerFactoryBean is used by repositories, the adapter is attached to the factory, and the property map is passed to the factory.

### Step 3: Check Startup Logs

Look for provider, dialect, persistence unit, and EntityManagerFactory details. If there are multiple factories, assign recognizable persistence unit names and verify repositories point to the right factory.

### Step 4: Run Integration Tests

An integration test should verify:

- The Spring context initializes EntityManagerFactory.
- Repositories can save and read entities.
- Transaction commit and rollback behave as expected.
- The schema is in a state consistent with the chosen ddl-auto.
- Performance properties such as JDBC batching take effect in real scenarios.

Do not conclude a property is active merely because the application starts successfully. A misspelled property can be silently ignored without causing an immediate error.

## 10. Common Errors and Troubleshooting

| Symptom | Possible Cause | Inspection Approach |
|---|---|---|
| Failed to create EntityManagerFactory | Missing provider dependency or adapter does not match provider | Check dependency tree, classpath, and persistence unit config |
| Hibernate property has no effect | Misspelled property name, wrong prefix, or app uses a different provider | Check final property map and documentation for the exact version |
| Hibernate cannot detect dialect | DataSource does not provide JDBC metadata or wrong driver | Check JDBC URL, driver, connection permissions; specify dialect only if truly needed |
| SQL does not appear | show-sql is off or logger category is not enabled | Check active profile and logger for the exact Hibernate version |
| Bind values do not appear | Bind logger not enabled or category name mismatches version | Check Hibernate 6 logger or running version |
| Schema changes unexpectedly | ddl-auto is set to update, create, or create-drop | Switch to an appropriate mode and use versioned migrations |
| Application uses the wrong provider | Multiple providers on classpath or ambiguous multi-persistence-unit config | Specify dependencies and adapters per factory |
| JpaTransactionManager does not coordinate properly | Transaction manager points to wrong EntityManagerFactory or missing tx config | Check bean names, persistence unit, and @EnableTransactionManagement |

## 11. Workflow for Selecting and Configuring Provider Properties

When adding a property:

1. Identify the actual provider and version from the dependency graph.
2. Check whether the property belongs to Jakarta Persistence or is provider-specific.
3. Look up the name, data type, valid values, and supported versions in the corresponding documentation.
4. Pick the right configuration point: spring.jpa.* for Boot options, spring.jpa.properties.* for provider properties, or setJpaProperties in manual factory configuration.
5. Declare a single authoritative source for each value; avoid duplicating across multiple profiles or configuration layers.
6. Start the application, inspect logs, and run integration tests.
7. Document the reason if using a custom dialect, uncommon property, or provider default override.

Do not copy a Hibernate configuration to EclipseLink or OpenJPA. Property names, meanings, valid values, and timing of application may differ.

## Checklist Before Merging

- [ ] JpaVendorAdapter matches the actual JPA provider.
- [ ] JpaVendorAdapter, JpaDialect, PersistenceProvider, and EntityManagerFactory are clearly distinguished.
- [ ] DataSource and provider are configured at the right responsibility layers.
- [ ] Standard JPA properties and provider-specific properties are categorized properly.
- [ ] Property names and values are verified against the exact provider version.
- [ ] Dialect is not hardcoded when the provider can auto-detect it and no custom behavior is required.
- [ ] ddl-auto update/create is not used as a production migration strategy.
- [ ] SQL and bind logging are enabled only in appropriate environments.
- [ ] EntityManagerFactory, repositories, and transactions are verified by integration tests.

## Conclusion

JpaVendorAdapter is the integration bridge between Spring ORM and a JPA provider. It supplies PersistenceProvider, JpaDialect, and vendor defaults during EntityManagerFactory creation. Properties such as hibernate.jdbc.batch_size or eclipselink.logging.level belong to specific providers, so exact names and versions must be used. In Spring Boot, prefer spring.jpa.* and spring.jpa.properties.*; in manual Spring ORM configuration, attach the adapter to LocalContainerEntityManagerFactoryBean and manage the property map explicitly. Always confirm the provider, effective configuration, and actual runtime behavior with logs and integration tests.