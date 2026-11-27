# Distinguishing Embedded Databases from Production Databases

In Spring Data JPA, an embedded database and a database used in deployment (typically a server database or external database) differ primarily in **how they run, where data is stored, and how the application connects**. Spring Data JPA still works through Repositories, JPA, and Hibernate; when switching database types, what typically changes are the JDBC driver, DataSource configuration, schema management, and operations.

## 1. Where the Database Sits in Spring Data JPA

Typical processing flow:

~~~text
Application
   |
   v
Spring Data Repository
   |
   v
JPA / EntityManager
   |
   v
Hibernate (JPA provider)
   |
   v
JDBC / DataSource
   |
   +----> H2 running embedded inside the application process
   |
   +----> PostgreSQL / MySQL running as a separate database service
~~~

- **Spring Data JPA** provides Repositories such as JpaRepository to work with entities.
- **JPA** defines the API and rules for mapping Java objects to database tables.
- **Hibernate** is typically the JPA provider executing ORM operations.
- **DataSource** supplies JDBC connections.
- **The database** actually stores and queries the data. It can run inside the same process as the application or as an independent service.

Therefore, Repositories usually do not need to be rewritten when switching from H2 to PostgreSQL. However, do not assume two database systems share identical SQL syntax, data types, locking behavior, or compatibility.

## 2. What Is an Embedded Database?

An embedded database is a database management system integrated into and running inside the application process or started directly by the application. The application typically does not need to connect to a standalone database server.

Common examples:

- **H2** in embedded or in-memory mode.
- **HSQLDB**.
- **Apache Derby**.

With in-memory H2, data usually resides in the memory of the Java process. When the application exits, in-memory data is lost. H2 also supports file-based storage mode; hence, not every embedded database loses data when the application shuts down.

Example H2 URL:

~~~properties
spring.datasource.url=jdbc:h2:mem:catalog
~~~

The application can initialize the database automatically at runtime. This is convenient for learning, demos, testing, or small applications needing simple setup.

## 3. What Is a Deployment Database?

In web applications or multi-user services, the database is usually deployed as a separate service. The Java application connects to that service over the network via JDBC.

Popular examples:

- **PostgreSQL**.
- **MySQL** or **MariaDB**.
- **Microsoft SQL Server**.
- **Oracle Database**.

A database server has a lifecycle independent of the application. The application can restart or scale to multiple instances while still connecting to the same database. Data is typically stored on disk or persistent storage services and managed using tools for backup, restore, monitoring, replication, and security.

Example PostgreSQL URL:

~~~properties
spring.datasource.url=jdbc:postgresql://db-host:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=change-me
~~~

In real deployment environments, credentials should be supplied via environment variables or a secret management system rather than writing real passwords into source code or committed configuration files.

## 4. Comparing the Two Approaches

| Criterion | Embedded Database | Server Database |
|---|---|---|
| Where it runs | Usually inside the application process | Runs as a separate service |
| Connection | Usually accessed directly within the same process | Application connects over the network via JDBC |
| Initial setup | Simple; usually only needs a dependency and URL configuration | Requires creating or provisioning a service, database, user, and permissions |
| Lifecycle | Usually tied to the application lifecycle | Independent of the application lifecycle |
| Storage | Can be in memory or local files | Usually uses disk or persistent storage services |
| Data after restart | Lost if using in-memory; if using file mode, it can be retained | Usually retained if storage and backups are configured properly |
| Multiple app instances | Each process may have its own separate database, depending on mode | Multiple instances can connect to the same database |
| Operations | Fewer components to administer | Requires managing connections, permissions, backups, recovery, monitoring, and security |
| Common use cases | Learning, demos, testing, single-process applications | Staging/production apps, multi-user or multi-instance systems |
| Scalability | Depends on engine and storage model; usually fits smaller scopes | Typically offers more options for concurrent connections, replication, and scaling |

These are common patterns, not absolute rules. A desktop application or single-user device app may use an embedded database in deployment. Conversely, PostgreSQL running in Docker on a development machine is still a server database, even though it runs only on a personal computer.

## 5. Distinguishing Database Product from Runtime Mode

Do not equate the product name with the deployment model:

- H2 can run in embedded, in-memory, file-based, or server mode.
- PostgreSQL typically runs as a standalone server.
- A file-backed database can still be an embedded database.
- A database running on the same machine as the application can still be an independent service.

The term "embedded" describes how the database is integrated and operated with the application. The term "production" describes the usage environment. These two concepts are not mutually exclusive product categories.

## 6. The Same Repository Can Work Across Multiple Databases

The following entity and Repository do not depend specifically on H2 or PostgreSQL:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

These snippets belong inside a Spring Boot project with the Spring Data JPA dependency; they are not standalone Java programs runnable with javac alone.

The Repository calls methods like save, findById, or findAll. Hibernate translates JPA operations into SQL matching the corresponding database and dialect. Even so, if the application uses native SQL queries, database-specific data types, or vendor-specific features, switching databases may require modifying SQL statements or mappings.

## 7. Configuring an Embedded Database with H2

In a Spring Boot project, you need the Spring Data JPA starter and the JDBC driver of the database in use. Example relevant Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <!-- Driver used when running the development profile with H2 -->
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Driver used when connecting to PostgreSQL -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Example src/main/resources/application-dev.properties file:

~~~properties
spring.datasource.url=jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true

spring.h2.console.enabled=true
spring.h2.console.path=/h2-console
~~~

Explanation:

- jdbc:h2:mem:catalog creates an in-memory database named catalog.
- DB_CLOSE_DELAY=-1 keeps the in-memory database alive until the JVM terminates, even when no open connections remain.
- ddl-auto=create-drop instructs Hibernate to create the schema at initialization and drop it when EntityManagerFactory closes. This is convenient for development or testing since data can be recreated.
- show-sql and format_sql help observe SQL during learning and debugging.
- H2 Console allows inspecting the database via a browser. Only enable it when needed in development and never expose the console in production.

If you want H2 data to survive restarts, you can use a file-based URL, for example:

~~~properties
spring.datasource.url=jdbc:h2:file:./data/catalog
~~~

Relative paths are resolved from the process working directory. Manage access permissions, backups, and file locations if using this approach long term.

## 8. Configuring a Server Database for Deployment Environments

Example application connecting to PostgreSQL using src/main/resources/application-prod.properties:

~~~properties
spring.datasource.url=${DB_URL}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}
spring.datasource.driver-class-name=org.postgresql.Driver

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=false
spring.jpa.open-in-view=false
~~~

Environment variables can be supplied when running the application:

~~~text
SPRING_PROFILES_ACTIVE=prod
DB_URL=jdbc:postgresql://db-host:5432/catalog
DB_USERNAME=catalog_app
DB_PASSWORD=<secret>
~~~

In the example above:

- DB_URL points to the server, port, and database to connect to. PostgreSQL's default port is 5432.
- The database and application account must be created and granted privileges beforehand or by a separate deployment step.
- ddl-auto=validate instructs Hibernate to verify that entity mappings match the existing schema. It does not create or update the schema.
- open-in-view=false disables keeping the persistence context open throughout handling and rendering a web request's response. With this setting, load necessary data inside services or transactions to avoid errors accessing lazy relationships after the session closes.

Do not write production passwords directly into application-prod.properties. Use environment variables, Docker/Kubernetes Secrets, or your deployment platform's secret manager. The application account should have only the minimum necessary privileges.

## 9. Selecting Configuration via Spring Profiles

Multiple configuration files can be maintained within the same project:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
~~~

Example application.properties:

~~~properties
spring.application.name=catalog-service
~~~

Running the development environment:

~~~text
SPRING_PROFILES_ACTIVE=dev
~~~

Running the deployment environment:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Spring Boot loads the shared configuration and the active profile's configuration. When deploying, verify which profile is actually active and ensure DB_URL points to the right database. If the URL is unset or the wrong profile is active, the application may use an unintended configuration.

When packaging an application for multiple environments, the same artifact can be reused while supplying different configurations and secrets for each environment. This avoids having to modify source code just to change database addresses.

## 10. Managing Schema and Seed Data

Spring Data JPA does not imply Hibernate always creates tables automatically. Creating, updating, and managing the schema must be configured explicitly.

Common values for spring.jpa.hibernate.ddl-auto:

| Value | Behavior |
|---|---|
| none | Hibernate does not automatically alter the schema |
| validate | Verifies entity mappings against the existing schema |
| update | Attempts to adjust the schema to match entities |
| create | Recreates the schema upon initialization |
| create-drop | Creates the schema on initialization and drops it on shutdown |

Usage guidelines:

- For temporary H2 used during learning or tests, create-drop is usually convenient.
- For deployment databases, manage schema changes with versioned migrations such as Flyway or Liquibase.
- Once migrations have created the schema, validate can catch mismatched mappings.
- Do not rely on update as a production migration workflow. Automatic updates cannot replace migrations with history, reviews, ordering control, and rollback plans.

Example Flyway migration src/main/resources/db/migration/V1__create_products.sql:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

Flyway executes migrations according to versions recorded in the database. When the schema needs changes, add a new migration rather than arbitrarily editing migrations already applied in shared environments. Migration syntax must be compatible with the target database; if a migration uses PostgreSQL-specific features, it cannot run on H2 by default.

Spring Boot also supports schema.sql and data.sql scripts for initializing schemas or sample data. Pay attention to script execution order relative to Hibernate. If scripts need to run after Hibernate creates the schema, you can configure spring.jpa.defer-datasource-initialization=true. For deployment environments, versioned migrations are generally easier to control than simple initialization scripts.

## 11. What to Check When Moving from H2 to PostgreSQL or MySQL

Using the same entities and Repositories does not guarantee every query will run identically. Before switching environments, check:

1. **Dialect and SQL syntax:** date/time functions, string concatenation, pagination, native queries, and result-limiting syntax may differ.
2. **Data types:** numeric types, booleans, JSON, UUIDs, dates/times, and timestamp precision may map differently.
3. **Key generation:** identity, sequences, and how Hibernate retrieves auto-generated keys may differ.
4. **Constraints and indexes:** check unique constraints, foreign keys, indexes, and null-handling rules.
5. **Case sensitivity and collation:** string comparison rules or table/column name handling may differ.
6. **Transactions and locking:** isolation levels, row locks, deadlocks, and concurrent transaction behavior must be tested on the target database.
7. **Migrations:** run all migrations on a fresh database and test upgrading from the schema version currently in use.
8. **Data:** if migrating existing data, plan export/import, type conversions, row-count reconciliation, and integrity checks.

H2 is very helpful for fast testing, but a test passing on H2 does not prove that SQL statements or migrations will definitely run on PostgreSQL. For production applications using PostgreSQL, maintain integration tests running against real PostgreSQL or a PostgreSQL container, for example via Testcontainers. Those tests verify the actual engine, dialect, and behavior close to the deployment environment.

## 12. Common Errors and Troubleshooting

**Application unexpectedly creates an H2 database in production**

- Check SPRING_PROFILES_ACTIVE.
- Check whether spring.datasource.url is loaded from the intended file or environment variable.
- Ensure the target database's JDBC driver is on the classpath.
- Configure the production URL explicitly and verify configuration right at startup.

**Cannot connect to the server database**

- Check hostname, port, and database name in the JDBC URL.
- Verify the database service is running and reachable from the application's runtime environment.
- Check firewalls, network policies, username, password, and account privileges.
- If running in Docker Compose, the hostname is usually the service name on the Compose network, not necessarily localhost.

**Missing table or schema mismatch**

- Check whether migrations ran successfully.
- Check which database/schema the application is connecting to.
- Check table names, column names, and entity mappings.
- Do not resolve this by arbitrarily switching to create on a database holding real data.

**Data disappears after restart**

- Check whether the URL uses jdbc:h2:mem:.
- In-memory databases lose data when the process ends; if persistence is required, use file mode or a server database with appropriate storage.
- Do not confuse DB_CLOSE_DELAY=-1 with persistent storage: this option only keeps the in-memory database while the JVM stays running.

**Tests pass with H2 but fail on PostgreSQL**

- Check native queries, data types, sequences/identity, and migrations.
- Run integration tests on the same database system and version close to production.
- Avoid relying on H2-specific behavior if the application will deploy on another database.

## 13. Practical Selection Guide

- **Learning Spring Data JPA or building demos:** use in-memory H2 to get started quickly and observe entities, Repositories, and SQL.
- **Unit tests or simple repository tests:** H2 can be used if the queries and features used are compatible.
- **Integration tests needing to mirror production:** prefer running the same engine as production, such as PostgreSQL via Testcontainers.
- **Multi-user web applications:** typically use PostgreSQL, MySQL, or a managed database service; configure connection pools, backups, monitoring, and security.
- **Desktop, offline, or single-process applications:** a file-backed embedded database can fit if backup, recovery, synchronization, and concurrency needs are clearly defined.

Before deploying, confirm the profile, JDBC URL, driver, account, and permissions; confirm the schema was created via migrations; confirm Hibernate uses validate or none according to your schema strategy; confirm integration tests ran on the target database; and confirm data has a backup/restore plan.

## 14. Conclusion

Embedded databases enable fast setup and reduce operational overhead, making them well-suited for learning, demos, testing, or single-process applications. Server databases are decoupled from the application lifecycle, support multi-instance architectures, and typically suit multi-user deployment systems. In Spring Data JPA, Repositories and entities can remain intact when switching databases, but you must configure the right driver and DataSource, manage schemas with migrations, and test target-database differences.