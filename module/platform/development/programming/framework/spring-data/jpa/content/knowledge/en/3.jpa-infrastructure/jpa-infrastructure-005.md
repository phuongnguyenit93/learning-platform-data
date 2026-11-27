# Configuring JPA with Java Without Spring Boot

Spring Data JPA can run in a standard Spring Framework application without Spring Boot. Without Boot, you can still use the Spring IoC container, Spring Data repositories, JPA, and Hibernate; however, you must manually declare the infrastructure components that Boot normally auto-configures.

This article demonstrates how to configure with Java Configuration: creating a DataSource, initializing an EntityManagerFactory, registering a transaction manager, enabling repository and component scanning, and starting a Spring ApplicationContext. The example uses Hibernate as the JPA provider and H2 as the database so it can run standalone.

## 1. Distinguishing the Components

Before configuring, you need to understand the role of each library:

- **Jakarta Persistence (JPA)** is the specification defining ORM APIs and rules: entities, mappings, persistence context, EntityManager, and persistence operations.
- **Hibernate ORM** is an implementation of JPA. It reads entity metadata, generates SQL, and communicates with the database over JDBC.
- **Spring Framework** provides the IoC container, dependency injection, bean management, transaction integration, and JPA integration support.
- **Spring Data JPA** builds a repository abstraction on top of JPA. It generates implementations for repository interfaces and provides derived queries, paging, sorting, and many other utilities.
- **DataSource** provides JDBC connections. Applications commonly use a connection pool such as HikariCP to reuse connections.
- **EntityManagerFactory** creates EntityManager instances. It is initialized once per persistence unit and typically lives for the entire application lifecycle.
- **EntityManager** performs operations on entities within a persistence context.
- **PlatformTransactionManager** connects Spring's transaction mechanism with JPA transactions.

Spring Data JPA does not replace the JPA provider or the database. Repositories call into JPA; a provider such as Hibernate translates operations into SQL; the JDBC driver sends SQL to the database.

## 2. What Must Be Configured Manually Without Spring Boot?

In a Spring Boot application, starters, auto-configuration, and externalized configuration automatically create many beans based on dependencies and settings. Without Boot, you must explicitly register:

1. Dependencies for Spring Framework, Spring Data JPA, the JPA provider, and the JDBC driver.
2. A DataSource pointing to the database.
3. A LocalContainerEntityManagerFactoryBean to build the EntityManagerFactory.
4. A JPA vendor adapter and Hibernate/JPA properties.
5. A JpaTransactionManager.
6. Repository scanning via @EnableJpaRepositories.
7. Service and component scanning via @ComponentScan or explicit bean declarations.
8. An ApplicationContext to start and manage bean lifecycles.

The initialization flow can be visualized as follows:

~~~text
AnnotationConfigApplicationContext
             |
             v
       Java @Configuration
             |
      +------+----------------+
      |                       |
      v                       v
   DataSource          EntityManagerFactory
                              |
                              v
                       Spring Data JPA
                       Repository proxies
                              |
                              v
                       JpaTransactionManager
~~~

DataSource must be provided before EntityManagerFactory can initialize. Repositories need EntityManagerFactory to create implementations. The transaction manager needs EntityManagerFactory to coordinate transactions.

## 3. Preparing Dependencies

The example below uses Java 17+, Spring Framework 6.1.13, Spring Data JPA 3.3.4, Hibernate ORM 6.5.3.Final, HikariCP 5.1.0, and H2 2.3.232. This is an illustrative set of versions from the same Jakarta generation; when starting a new project, choose Spring Framework, Spring Data, and Hibernate versions according to the compatibility matrix of the Spring Data release train in use.

Required dependencies:

| Artifact | Purpose |
|---|---|
| spring-context | ApplicationContext, @Configuration, @ComponentScan |
| spring-orm | LocalContainerEntityManagerFactoryBean and JpaTransactionManager |
| spring-jdbc | DataSource and JDBC integration |
| spring-data-jpa | JpaRepository and @EnableJpaRepositories |
| hibernate-core | JPA provider |
| jakarta.persistence-api | JPA annotations and APIs |
| HikariCP | Connection pool |
| H2 | In-memory database for the example |
| slf4j-simple | Simple logging provider for the example |

Minimal Maven example:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>jpa-without-boot</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.1.13</spring-framework.version>
        <spring-data-jpa.version>3.3.4</spring-data-jpa.version>
        <hibernate.version>6.5.3.Final</hibernate.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-orm</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-jpa</artifactId>
            <version>${spring-data-jpa.version}</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-core</artifactId>
            <version>${hibernate.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.persistence</groupId>
            <artifactId>jakarta.persistence-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.16</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

There is no spring-boot-starter or Spring Boot plugin in this project. Dependencies are declared directly so you can clearly see the components the application uses.

## 4. Package Organization for the Example

Source code can be organized as follows:

~~~text
src/main/java/
└── example/
    ├── Main.java
    ├── config/
    │   └── JpaConfig.java
    ├── domain/
    │   └── Customer.java
    ├── repository/
    │   └── CustomerRepository.java
    └── service/
        └── CustomerService.java

src/main/resources/
└── application.properties
~~~

In the example:

- **config** contains Spring and persistence configuration.
- **domain** contains entities.
- **repository** contains Spring Data JPA interfaces.
- **service** contains business logic.
- **Main** initializes the ApplicationContext.
- **application.properties** contains database connection details.

## 5. Declaring Database Connection Settings

Create **src/main/resources/application.properties**:

~~~properties
app.datasource.driver-class-name=org.h2.Driver
app.datasource.url=jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1
app.datasource.username=sa
app.datasource.password=
~~~

H2 runs in memory, so the example does not require installing a database server. The **DB_CLOSE_DELAY=-1** parameter keeps the in-memory database alive until the JVM exits, even if a connection is temporarily closed.

In real environments, URL, username, and password must come from environment configuration or a secret manager. Do not commit production passwords to the repository.

Without Boot, **@PropertySource** can load properties files and Spring's **Environment** reads the values. You can also register another **PropertySource** manually or use system properties and environment variables.

## 6. Creating Java Configuration for JPA

This is the most important part. Create **JpaConfig.java**:

~~~java
package example.config;

import example.domain.Customer;
import example.repository.CustomerRepository;
import example.service.CustomerService;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.core.env.Environment;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import javax.sql.DataSource;
import java.util.Properties;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:application.properties")
@ComponentScan(basePackageClasses = CustomerService.class)
@EnableTransactionManagement
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class,
    entityManagerFactoryRef = "entityManagerFactory",
    transactionManagerRef = "transactionManager"
)
public class JpaConfig {

    @Bean(destroyMethod = "close")
    public HikariDataSource dataSource(Environment environment) {
        HikariConfig config = new HikariConfig();

        config.setDriverClassName(
            environment.getRequiredProperty(
                "app.datasource.driver-class-name"
            )
        );
        config.setJdbcUrl(
            environment.getRequiredProperty("app.datasource.url")
        );
        config.setUsername(
            environment.getRequiredProperty("app.datasource.username")
        );
        config.setPassword(
            environment.getProperty("app.datasource.password", "")
        );

        config.setMaximumPoolSize(5);
        config.setMinimumIdle(1);

        return new HikariDataSource(config);
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean entityManagerFactory(
        DataSource dataSource
    ) {
        LocalContainerEntityManagerFactoryBean factory =
            new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan(Customer.class.getPackageName());
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());

        Properties properties = new Properties();
        properties.setProperty("hibernate.hbm2ddl.auto", "create-drop");
        properties.setProperty("hibernate.show_sql", "false");
        properties.setProperty("hibernate.jdbc.time_zone", "UTC");

        factory.setJpaProperties(properties);

        return factory;
    }

    @Bean
    public PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory
    ) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

Analyzing each part:

### 6.1. @Configuration

**@Configuration** marks a class containing bean declaration methods. Spring reads the class metadata and invokes **@Bean** methods to register objects into the ApplicationContext.

**proxyBeanMethods = false** disables proxying between **@Bean** methods in the configuration class. In this example, each bean receives its dependencies via method parameters, so there is no need to call another **@Bean** method directly.

### 6.2. @PropertySource and Environment

**@PropertySource("classpath:application.properties")** loads the configuration file into the Environment.

Spring injects Environment into the **dataSource()** method. This method reads the URL, username, password, and driver using **getRequiredProperty()** or **getProperty()**.

- **getRequiredProperty()** throws an error if a required property does not exist.
- **getProperty(key, defaultValue)** returns a default value when the property is absent.

This separates configuration from source code. In production, values can be supplied via system properties or environment variables. For example, the environment variable **APP_DATASOURCE_URL** can be mapped to the property **app.datasource.url** by Spring's default SystemEnvironmentPropertySource.

### 6.3. DataSource and HikariCP

**DataSource** is the JDBC abstraction that provides connections. HikariCP implements DataSource and manages the connection pool.

Parameters in the example:

- **setJdbcUrl()** declares the JDBC URL.
- **setUsername()** and **setPassword()** declare connection credentials.
- **setDriverClassName()** specifies the JDBC driver.
- **setMaximumPoolSize(5)** limits the maximum number of connections in the pool.
- **setMinimumIdle(1)** sets the minimum number of idle connections.

Pool size must be chosen based on application load, database connection limits, and the number of application instances. Do not increase the pool arbitrarily because each connection also consumes resources on the database side.

**@Bean(destroyMethod = "close")** instructs Spring to close HikariDataSource when ApplicationContext shuts down. This allows the pool to release connections properly according to lifecycle.

### 6.4. LocalContainerEntityManagerFactoryBean

This is Spring's FactoryBean used to create and manage a JPA EntityManagerFactory.

Key configuration settings:

- **setDataSource(dataSource)** connects the persistence unit to the DataSource.
- **setPackagesToScan(...)** specifies the packages containing entities to discover.
- **setJpaVendorAdapter(...)** declares the adapter for the JPA provider.
- **setJpaProperties(...)** passes provider-specific or JPA properties.

**HibernateJpaVendorAdapter** helps Spring ORM integrate with Hibernate. In this example, Hibernate can auto-detect the dialect from JDBC metadata provided by H2. For special cases, the dialect can be configured explicitly via the **hibernate.dialect** property.

The method name **entityManagerFactory** is also the default bean name expected by Spring Data JPA. If you rename the bean, update **entityManagerFactoryRef** accordingly.

### 6.5. Hibernate Properties

**hibernate.hbm2ddl.auto** controls how Hibernate handles the schema:

- **create**: recreates the schema on startup.
- **create-drop**: creates the schema on startup and drops it when SessionFactory/EntityManagerFactory closes.
- **update**: attempts to adjust the schema to match mappings.
- **validate**: checks whether the schema matches the mappings.
- **none**: does not automatically create, update, or validate the schema.

The example uses **create-drop** for convenience with an in-memory database. In production, Flyway or Liquibase is typically used to manage migrations, and Hibernate is set to **validate** or **none**. Do not rely on **update** as a production migration tool because schema changes need to be controlled and reviewed.

**hibernate.show_sql=false** disables Hibernate's direct SQL printing. When debugging, enable appropriate logging for Hibernate SQL and bind parameters; avoid exposing sensitive data in production logs.

**hibernate.jdbc.time_zone=UTC** instructs Hibernate to use UTC for time-related JDBC operations on supported types. The application still needs consistent rules for representing time across the domain and database.

### 6.6. JpaTransactionManager

**JpaTransactionManager** implements **PlatformTransactionManager** and manages transactions for a single JPA EntityManagerFactory.

A bean named **transactionManager** is the default name looked up by Spring Data JPA and the transaction infrastructure. The **@EnableTransactionManagement** annotation activates **@Transactional** processing via Spring proxies.

If the application has multiple EntityManagerFactories or multiple databases, you usually need to declare separate transaction managers and specify which repository uses which persistence unit.

## 7. Enabling Repository and Component Scanning

In the configuration class:

**@EnableJpaRepositories(basePackageClasses = CustomerRepository.class)** instructs Spring Data JPA to scan the package containing the marker interface CustomerRepository and create implementation proxies for discovered repositories.

You do not need to manually write a class implementing JpaRepository. Spring Data creates repository beans during ApplicationContext initialization.

**@ComponentScan(basePackageClasses = CustomerService.class)** instructs Spring to scan the package containing the service marker to find standard beans such as **@Service**, **@Component**, and **@Repository**.

Entities are discovered via **setPackagesToScan()** on EntityManagerFactory. This is a separate mechanism, not synonymous with component scanning.

Three scanning scopes must be configured properly:

| Mechanism | Discovered Components |
|---|---|
| @ComponentScan | Services, components, and other Spring beans |
| @EnableJpaRepositories | Spring Data repository interfaces |
| setPackagesToScan | JPA entities |

If a package is outside the scan scope, the corresponding bean or entity will not be discovered. Using **basePackageClasses** avoids relying on hand-typed package strings and makes package renaming easier.

## 8. Creating the Entity and Repository

Create the entity **Customer.java**:

~~~java
package example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
        // JPA requires a no-arg constructor with appropriate visibility.
    }

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getName() {
        return name;
    }
}
~~~

The entity must be placed in a package scanned by EntityManagerFactory. JPA uses annotations to map the class and fields to tables, columns, primary keys, and ID generation strategies.

Create **CustomerRepository.java**:

~~~java
package example.repository;

import example.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
    extends JpaRepository<Customer, Long> {

    boolean existsByEmail(String email);
}
~~~

Spring Data JPA will create an implementation for this interface. **JpaRepository<Customer, Long>** specifies Customer as the entity and Long as the ID type. The **existsByEmail** method is a derived query: Spring Data parses the method name to build a query checking email existence.

## 9. Creating the Service and Using Transactions

Create **CustomerService.java**:

~~~java
package example.service;

import example.domain.Customer;
import example.repository.CustomerRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email, String name) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }

        if (repository.existsByEmail(email)) {
            throw new IllegalArgumentException("Email already exists");
        }

        return repository.save(new Customer(email, name));
    }

    @Transactional(readOnly = true)
    public long count() {
        return repository.count();
    }
}
~~~

Constructor injection makes dependencies explicit and facilitates unit testing. The Service does not instantiate the repository with **new**; Spring provides the repository bean created by Spring Data JPA.

**@Transactional** on **register()** creates a transaction boundary for the business operation. Checking the email and saving the Customer participate in the service-managed transaction.

**@Transactional(readOnly = true)** indicates the method is read-only. This is a hint to the transaction manager and provider; do not treat it as an absolute protection mechanism blocking every write statement.

Spring's common default is rolling back on unchecked exceptions and Errors. If rollback is needed for checked exceptions, configure **rollbackFor** accordingly.

An important note: transaction proxies only apply when calls go through the Spring proxy. Calling a **@Transactional** method from another method in the same object (self-invocation) normally bypasses the proxy, and thus does not trigger a new transaction boundary as expected.

## 10. Starting the ApplicationContext

Create **Main.java**:

~~~java
package example;

import example.config.JpaConfig;
import example.domain.Customer;
import example.service.CustomerService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        System.setProperty(
            "org.slf4j.simpleLogger.defaultLogLevel",
            "warn"
        );

        try (var context =
                 new AnnotationConfigApplicationContext(JpaConfig.class)) {

            CustomerService service =
                context.getBean(CustomerService.class);

            Customer customer =
                service.register("an@example.com", "An");

            System.out.println("created=" + (customer.getId() != null));
            System.out.println("count=" + service.count());
        }
    }
}
~~~

**AnnotationConfigApplicationContext** creates a Spring container from a Java Configuration class. During context initialization, Spring registers beans, creates the DataSource, EntityManagerFactory, transaction manager, and repository proxies. Then **getBean()** retrieves CustomerService with its injected dependencies.

The try-with-resources block closes the ApplicationContext when finished. Spring closes beans with lifecycle callbacks, including HikariDataSource and EntityManagerFactory.

Run from the directory containing **pom.xml**:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.Main
~~~

The two lines explicitly printed by the program:

~~~text
created=true
count=1
~~~

**created=true** indicates the database assigned an ID to the entity after saving. **count=1** indicates the repository queried one record in the customers table. Framework logs may appear depending on the environment's logging configuration.

## 11. Lifecycle of a Repository Operation

When calling **service.register(...)**, the basic execution flow is as follows:

1. The call goes through CustomerService's Spring proxy.
2. The transaction manager starts or joins an appropriate transaction.
3. The Service calls **CustomerRepository.existsByEmail(...)**.
4. The repository proxy uses EntityManager to execute the query.
5. Hibernate generates SQL and the JDBC driver sends SQL to the database.
6. If the email does not exist, the service creates Customer and calls **save()**.
7. JPA manages the entity in the persistence context and synchronizes changes when a flush is needed.
8. The transaction commits when the method completes successfully; if a rollback-triggering error occurs, the transaction manager handles rollback according to rules.
9. The result is returned to the caller.

**save()** does not necessarily emit an INSERT statement immediately at the call line. For a new entity, the JPA provider may defer SQL until flush or commit. Execution timing depends on the ID strategy, entity state, and persistence context synchronization needs.

## 12. EntityManager and Direct Injection When Needed

Spring ORM also supports injecting EntityManager using **@PersistenceContext**:

~~~java
package example.repository;

import example.domain.Customer;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerLookup {

    @PersistenceContext
    private EntityManager entityManager;

    public Customer findById(Long id) {
        return entityManager.find(Customer.class, id);
    }
}
~~~

Spring supplies an EntityManager proxy aligned with the current transaction and persistence context. Do not manually create a single EntityManager shared across threads or hold an EntityManager long-term in a singleton field.

When using Spring Data JPA, prefer repositories for standard CRUD and query operations. Use EntityManager directly when you need JPQL, Criteria API, bulk operations, or persistence features that the repository abstraction does not express clearly.

## 13. Configuration When Using a Real Database

To connect to PostgreSQL, MySQL, or another database, you need to:

1. Add the corresponding JDBC driver to dependencies.
2. Replace the JDBC URL, driver class, username, and password.
3. Configure pool size and timeouts appropriate for the workload.
4. Decide how to manage schemas, preferring versioned migrations.
5. Choose data types and ID strategies compatible with the database.
6. Verify application account privileges, granting only required permissions.

For example, with PostgreSQL, the JDBC URL typically looks like **jdbc:postgresql://host:5432/database**. The corresponding driver is **org.postgresql.Driver**; the dependency is **org.postgresql:postgresql**.

Specifying a Hibernate dialect is not required in every case. Hibernate 6 normally detects the database from JDBC metadata. If you must declare it explicitly, use the dialect matching the running Hibernate version.

In production environments, set **hibernate.hbm2ddl.auto=validate** or **none** according to the chosen schema workflow. The migration tool should be responsible for schema changes; Hibernate should validate mappings or perform persistence.

## 14. Multiple Persistence Units or Multiple Databases

Advanced applications may need multiple DataSources and multiple EntityManagerFactories, for instance an orders database and a reporting database.

In that case, you must separately declare:

- Each DataSource.
- Each LocalContainerEntityManagerFactoryBean and persistence unit.
- Each PlatformTransactionManager.
- Respective repository package scopes.
- **entityManagerFactoryRef** and **transactionManagerRef** for each repository group.

Do not let a repository accidentally use the wrong EntityManagerFactory. Meaningful bean naming and explicit package configuration help avoid startup errors or transactions hitting the wrong database.

## 15. Comparing Pure Java Configuration vs. Spring Boot

| Task | Spring Framework Without Boot | Spring Boot |
|---|---|---|
| Context initialization | Create AnnotationConfigApplicationContext or appropriate context | SpringApplication.run(...) |
| DataSource | Declare bean and connection pool manually | Usually auto-configured from dependencies and properties |
| EntityManagerFactory | Declare LocalContainerEntityManagerFactoryBean manually | Usually auto-configured |
| Transaction manager | Declare JpaTransactionManager manually | Usually auto-configured |
| Repository scanning | Declare @EnableJpaRepositories | Can be auto-configured or declared explicitly |
| Component scanning | Declare @ComponentScan | @SpringBootApplication includes component scanning |
| External configuration | Environment, @PropertySource, system properties, or custom PropertySource | Adds Boot's binding and externalized config mechanisms |
| Dependencies | Select individual artifacts | Can use starters |

Not using Boot does not mean not using Spring. You still use Spring Framework and Spring Data JPA; only the infrastructure beans must be configured explicitly.

## 16. Common Errors and Checks

**1. Repository bean not found**

Check whether the interface's package lies within **@EnableJpaRepositories** scope. Verify the interface extends an appropriate repository interface and ApplicationContext loaded the right configuration class.

**2. Entity not found or Unknown entity reported**

Check whether the entity package was passed into **setPackagesToScan()**. Ensure the entity has **@Entity**, has a primary key **@Id**, and resides in the correct persistence unit.

**3. Failed to create EntityManagerFactory**

Check DataSource, JDBC URL, driver, username/password, Hibernate dependencies, and JPA properties. Inspect the root cause in the stack trace; initialization errors may involve database connectivity, dialect, mapping, or schema.

**4. Transaction manager not found**

Check whether the **transactionManager** bean is registered and repositories reference the right **transactionManagerRef**. Check **@EnableTransactionManagement** and spring-tx/spring-orm dependencies.

**5. @Transactional has no effect**

Ensure the object is managed by Spring, the method is called through a Spring proxy, and transaction management is enabled. Check self-invocation, method visibility, and proxy configuration.

**6. Database reports missing table or wrong column**

Compare entity mappings with the actual schema. Check whether migrations ran and whether data types and table/column names match. In validate mode, Hibernate fails if the schema is incompatible.

**7. Connection pool exhausted or connections held too long**

Check long-running transactions, unreturned connections, pool size, timeouts, and database load. Do not fix it by increasing pool size before identifying the root cause.

**8. Mixing up javax.persistence and jakarta.persistence**

Spring Framework 6 and Spring Data JPA 3 use the Jakarta namespace (**jakarta.persistence.***). Older examples based on **javax.persistence.*** belong to the previous generation and cannot be arbitrarily mixed with the Jakarta stack.

## 17. Important Operational Principles

- Use one shared EntityManagerFactory per persistence unit in ordinary applications; do not create a new one per request.
- Let Spring manage the lifecycle of DataSource, EntityManagerFactory, and the transaction manager.
- Never share a real EntityManager across multiple threads.
- Place transactions at business boundaries, typically in services.
- Do not keep transactions open while calling external APIs or waiting for user input.
- Use versioned migrations for production schemas.
- Do not log passwords, tokens, or sensitive bind parameters.
- Size the pool according to database limits and total application instances.
- Inspect repository queries and execution plans when performance issues arise.
- Keep database configuration separate from source code and manage secrets via appropriate mechanisms.

## 18. Practice Exercise

Extend the Customer example into a small application:

1. Add an Order entity and a many-to-one relationship with Customer.
2. Create OrderRepository extending JpaRepository.
3. Write OrderService with constructor injection and @Transactional.
4. Create a query finding a Customer's orders by email.
5. Run the application with H2, then switch the DataSource to PostgreSQL.
6. Replace **create-drop** with a table-creating migration and Hibernate **validate**.
7. Try removing **@EnableTransactionManagement** and observe behavior when multiple data operations run in one service method.
8. Write an integration test initializing ApplicationContext and saving/reading an entity.

Through this exercise, be able to explain where each bean is created, which bean depends on which, where repositories obtain EntityManager, and how the transaction manager connects to the persistence unit.

## 19. Self-Assessment Checklist

- [ ] I can distinguish JPA, Hibernate, Spring Framework, and Spring Data JPA.
- [ ] I know why an application without Boot must declare a DataSource.
- [ ] I understand the role of LocalContainerEntityManagerFactoryBean.
- [ ] I know how to configure entity packages using **setPackagesToScan()**.
- [ ] I understand HibernateJpaVendorAdapter and JPA properties.
- [ ] I know why JpaTransactionManager is needed.
- [ ] I can distinguish @ComponentScan and @EnableJpaRepositories.
- [ ] I can start an AnnotationConfigApplicationContext.
- [ ] I understand how Spring injects repositories into services.
- [ ] I understand transaction proxies and the self-invocation issue.
- [ ] I know how demo schema settings differ from production schema settings.
- [ ] I can trace stack traces when DataSource or EntityManagerFactory initialization fails.

## 20. Review Questions

**1. Why can Spring Data JPA still be used without Spring Boot?**

Because Spring Data JPA is an integration library for Spring Framework and JPA. Boot primarily provides bootstrapping and auto-configuration; it is not a prerequisite for repositories to work.

**2. What does LocalContainerEntityManagerFactoryBean do?**

It integrates EntityManagerFactory lifecycle with Spring and configures the DataSource, entity packages, JPA provider, and persistence properties.

**3. Why is JpaTransactionManager needed?**

It connects Spring's transaction mechanism with EntityManagerFactory so `@Transactional` methods manage JPA transactions properly.

**4. How does @EnableJpaRepositories differ from @ComponentScan?**

@EnableJpaRepositories scans for Spring Data interfaces and creates repository proxies. @ComponentScan scans for regular Spring components such as services and components.

**5. Why should create-drop not be used in production?**

Because the schema can be recreated or dropped with the application lifecycle, causing data loss. Production should use versioned migrations and an appropriate Hibernate setting such as validate or none.

**6. Why should you not manually create an EntityManager in each service?**

Because Spring needs to manage the EntityManager bound to the current transaction and persistence context. Creating it manually risks resource leaks, broken transaction boundaries, and desynchronization with repositories.

Once you understand and can configure these beans yourself, you have grasped how Spring Data JPA works internally in a Spring Framework application without Spring Boot.