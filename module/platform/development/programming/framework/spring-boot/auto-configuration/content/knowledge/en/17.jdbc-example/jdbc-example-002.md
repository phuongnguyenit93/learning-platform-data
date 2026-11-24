# JDBC Classpath, Drivers, and Embedded Data Sources Across Configuration Branches

## 1. Goal: Understand why Spring Boot selects a specific DataSource

When adding a JDBC dependency to a Spring Boot application, many expect Spring to “automatically connect to the database”. In practice, Spring Boot must evaluate multiple conditions before registering a DataSource bean:

- Are the JDBC API and Spring JDBC present on the classpath?
- Has the application already declared its own DataSource/XADataSource?
- Is there an R2DBC ConnectionFactory bean causing JDBC auto-configuration to yield?
- Which connection pool classes are present: HikariCP, Tomcat JDBC, Commons DBCP2, or Oracle UCP?
- Is the database driver on the runtime classpath?
- Is an explicit connection URL provided, or does Spring need to infer a URL for an embedded database?
- If multiple embedded engines are present, is H2, HSQL, or Derby chosen?

This lesson belongs to the **JDBC Example** group, focusing on the relationship between the **classpath**, **JDBC driver**, **connection pool**, **embedded database**, and the branches inside Spring Boot 3.3's **DataSourceAutoConfiguration**.

After this lesson, you can read the conditions to understand why Boot takes the pooled or embedded branch, see why H2 can run underneath HikariCP, recognize missing-driver errors, and verify with a runnable Java 17+ application.

## 2. Distinguish four components: JDBC API, driver, database engine, and pool

These four concepts are related, but they do not replace one another.

| Component | Role | Examples |
|---|---|---|
| JDBC API | Java contract for applications to work with SQL connections, statements, and results | javax.sql.DataSource, java.sql.Connection, java.sql.Driver |
| JDBC driver | Protocol implementation allowing Java to communicate with a specific database management system | org.h2.Driver, org.postgresql.Driver |
| Database engine | Software that actually stores data and executes SQL | H2, PostgreSQL, MySQL, SQL Server |
| Connection pool / DataSource implementation | Manages and dispenses connections to the application | HikariCP, Tomcat JDBC Pool, Commons DBCP2 |

Example with PostgreSQL:

- The application calls JdbcTemplate or the JDBC API.
- HikariCP manages the pool and provides a Connection.
- The PostgreSQL JDBC Driver translates JDBC calls into communication with the server.
- The PostgreSQL server executes SQL and stores data.

**HikariCP is not the PostgreSQL driver.** Adding HikariCP does not automatically add the PostgreSQL driver; adding the PostgreSQL driver also does not automatically create a connection pool.

With embedded H2, both the database engine and the JDBC driver reside in the same H2 dependency. H2 can run inside the Java process, typically using a URL of the form jdbc:h2:mem:... to create an in-memory database.

### What does the classpath need?

- **DataSource** belongs to the Java API, located in the JDK's java.sql module.
- **EmbeddedDatabaseType**, **JdbcTemplate**, and **EmbeddedDatabaseBuilder** belong to Spring JDBC (the spring-jdbc artifact).
- **HikariDataSource** belongs to HikariCP.
- **org.h2.Driver** and the H2 engine belong to the com.h2database:h2 artifact.
- The PostgreSQL driver belongs to the org.postgresql:postgresql artifact.

An important point in Spring Boot 3.3: DataSourceAutoConfiguration has a classpath condition on both DataSource and EmbeddedDatabaseType. Because EmbeddedDatabaseType belongs to Spring JDBC, having only the JDBC API and a vendor driver without spring-jdbc will fail Boot's standard JDBC auto-configuration classpath condition.

For typical applications, using spring-boot-starter-jdbc is convenient because the starter brings in Spring JDBC and HikariCP. The external database driver must still be added separately.

## 3. DataSourceAutoConfiguration: outer-layer conditions

In Spring Boot 3.3.13, DataSourceAutoConfiguration has key conditions:

    @AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
    @ConditionalOnClass({
        DataSource.class,
        EmbeddedDatabaseType.class
    })
    @ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")
    @EnableConfigurationProperties(DataSourceProperties.class)

You can read them step by step:

1. **DataSource.class is on the classpath:** the JDK provides the JDBC DataSource API.
2. **EmbeddedDatabaseType.class is on the classpath:** the application has Spring JDBC.
3. **No R2DBC ConnectionFactory bean:** if the context already has a ConnectionFactory for R2DBC, default JDBC DataSource auto-configuration yields. This is how Boot avoids automatically enabling blocking JDBC in an application already using R2DBC.
4. **DataSourceProperties is bound:** standard properties under the spring.datasource prefix are bound into the configuration object.
5. **Ordered before SQL initialization:** DataSource is processed before script-based database initialization configuration.

Note: outer-layer conditions only determine whether DataSourceAutoConfiguration is eligible to participate. Actual DataSource bean creation happens in nested configurations and also depends on pools, drivers, URLs, and user-provided beans.

### When does JDBC auto-configuration not run?

| Situation | Consequence |
|---|---|
| Missing spring-jdbc, so EmbeddedDatabaseType is absent | The classpath condition on DataSourceAutoConfiguration does not match |
| R2DBC ConnectionFactory bean is present | Default JDBC DataSource auto-configuration backs off |
| Only H2 is missing, but URL and PostgreSQL driver are present | Can still create a pooled DataSource for PostgreSQL |
| Application declares its own DataSource bean | Default embedded/pooled branches do not create an additional DataSource |
| XADataSource bean is present | Embedded/pooled branches also back off via the missing-bean condition |

If a reactive application has an R2DBC ConnectionFactory but intentionally wants to use JDBC as well, the Spring Boot documentation allows explicitly importing DataSourceAutoConfiguration. Only do this when the architecture accepts using blocking JDBC alongside R2DBC.

## 4. Two main branches inside DataSourceAutoConfiguration

Boot 3.3.13 has two main nested configurations:

- **PooledDataSourceConfiguration**
- **EmbeddedDatabaseConfiguration**

Both have a condition not to create a default DataSource when a matching DataSource or XADataSource bean already exists.

Overview diagram:

    DataSourceAutoConfiguration
        |
        |-- classpath conditions + no R2DBC ConnectionFactory
        |
        +--> PooledDataSourceConfiguration
        |       |
        |       |-- spring.datasource.type is set
        |       |       OR
        |       |-- DataSourceBuilder finds a supported pool
        |       |
        |       +--> Hikari / Tomcat / DBCP2 / Oracle UCP / Generic
        |
        +--> EmbeddedDatabaseConfiguration
                |
                |-- spring.datasource.url has no text value
                |-- pooled branch did not match
                |-- embedded engine H2/HSQL/Derby found
                |
                +--> EmbeddedDataSourceConfiguration

This is the decision model for the two default branches. A user-provided DataSource bean can prevent both branches from being applied.

## 5. Pooled branch: selecting a connection pool from the classpath

PooledDataSourceConfiguration is considered when PooledDataSourceCondition matches. In Spring Boot 3.3.13, this condition matches if:

- The **spring.datasource.type** property has a value; or
- DataSourceBuilder finds a supported DataSource implementation on the classpath.

This is a logical OR. Only one of the two sub-branches needs to match.

### 5.1. Default pool selection order

If spring.datasource.type is not set, Spring Boot selects in priority order:

| Priority | Connection pool | Condition |
|---:|---|---|
| 1 | HikariCP | Hikari is on the classpath |
| 2 | Tomcat JDBC Pool | Hikari is absent, Tomcat pool is present |
| 3 | Commons DBCP2 | Both pools above are absent, DBCP2 is present |
| 4 | Oracle UCP | Previous options are absent, UCP is present |

If you use spring-boot-starter-jdbc or spring-boot-starter-data-jpa, HikariCP is usually pulled into the dependency tree. Therefore, when using these starters, Hikari is usually the default choice.

If you want to select a specific pool, you can configure:

    spring.datasource.type=com.zaxxer.hikari.HikariDataSource

The type value is the class name of the DataSource implementation. That class must exist on the runtime classpath. If you set a class that is not present, the application will fail when creating the DataSource.

Properties specific to each pool have their own namespaces:

    spring.datasource.hikari.maximum-pool-size=20
    spring.datasource.hikari.minimum-idle=2
    spring.datasource.tomcat.max-active=50
    spring.datasource.dbcp2.max-total=30

Only use properties for the pool that is actually selected. Setting spring.datasource.hikari.* does not put Hikari on the classpath and does not force Boot to choose Hikari if the Hikari class is missing.

### 5.2. Pool presence does not mean the driver is present

PooledDataSourceCondition checks whether a DataSource implementation can be found; it does not replace checking the database driver.

Example:

- HikariCP is on the classpath.
- spring.datasource.url is jdbc:postgresql://localhost:5432/inventory.
- But the org.postgresql:postgresql dependency is missing.

Boot can still choose the pooled branch because Hikari exists. When determining the driver or initializing the DataSource, the application fails to find a suitable driver and startup fails.

**The pool manages connections; the driver connects to the database.** You need both when using the pooled branch with a regular JDBC database.

## 6. Embedded branch: conditions to create an EmbeddedDatabase

EmbeddedDatabaseConfiguration has EmbeddedDatabaseCondition. In Spring Boot 3.3.13, this condition checks in order:

1. If spring.datasource.url has a value containing text, the embedded branch does not match.
2. If PooledDataSourceCondition already matched, the embedded branch does not match.
3. If no suitable embedded database engine is found on the classpath, the condition does not match.
4. If an embedded engine is found, the condition matches and Boot imports EmbeddedDataSourceConfiguration.

Spring Boot 3.3 supports the following embedded engines:

| Engine | Typical dependency | Driver |
|---|---|---|
| H2 | com.h2database:h2 | org.h2.Driver |
| HSQLDB | org.hsqldb:hsqldb | org.hsqldb.jdbc.JDBCDriver |
| Apache Derby | org.apache.derby:derby | org.apache.derby.iapi.jdbc.AutoloadedDriver |

Derby is noted as deprecated in Spring Boot 3.3's SQL database documentation. For new examples, H2 is usually the simplest choice.

If multiple embedded engines are on the classpath, choose the engine using:

    spring.datasource.embedded-database-connection=h2

Corresponding values can be h2, hsqldb, derby, or none. Set none to disable embedded database detection.

If there is no pool and no spring.datasource.url, but H2 is on the classpath, Boot can create an EmbeddedDatabase via Spring JDBC's EmbeddedDatabaseBuilder. You do not need to supply a JDBC URL yourself.

### 6.1. Embedded database does not always mean an EmbeddedDatabase bean

This is a very easy point to confuse:

**Embedded database engine** and **DataSource bean type** are two different concepts.

When H2 is on the classpath while HikariCP is also present, PooledDataSourceCondition matches. EmbeddedDatabaseCondition sees that the pooled branch already matched, so it does not run the EmbeddedDatabaseConfiguration branch. However, DataSourceProperties can still determine the in-memory H2 URL; HikariDataSource is created and connects to that H2 engine.

The result is:

- Database engine: embedded H2.
- DataSource bean: HikariDataSource.
- Connection pool: HikariCP.
- JDBC driver: H2 Driver.

Only when the pooled branch does not match and an embedded engine is present does Boot directly take the EmbeddedDatabaseConfiguration branch to create an EmbeddedDatabase.

### 6.2. Effect of spring.datasource.url

A non-empty URL prevents EmbeddedDatabaseCondition from matching. In that case:

- If a pool or a valid spring.datasource.type is present, Boot can use the pooled branch with the declared URL.
- If there is no pool and no type, the pooled branch does not match; the embedded branch is also blocked by the URL. Then Boot cannot automatically create a DataSource through the two default branches.

Configuration example:

    spring.datasource.url=jdbc:postgresql://localhost:5432/inventory

means the application is pointing to an external JDBC target. It needs the PostgreSQL driver and a suitable DataSource implementation on the classpath or specified via type.

### 6.3. Embedded databases and database names

In-memory H2 typically has a URL like:

    jdbc:h2:mem:demo

An in-memory database normally does not persist data after the process exits. If configuring an embedded URL manually, pay attention to database lifecycle. Spring Boot documentation recommends controlling H2's auto-close behavior with DB_CLOSE_ON_EXIT=FALSE when manually configuring the URL, so Spring Boot controls when the database closes after the application stops using it.

In tests, multiple application contexts can accidentally reuse the same embedded database. Set:

    spring.datasource.generate-unique-name=true

to generate a distinct database name for each context when appropriate.

## 7. JDBC driver: detection, declaration, and classpath errors

A driver is a class implementing java.sql.Driver. Spring Boot uses DataSourceProperties to determine the driver based on configuration and the Environment.

### 7.1. Do you need to declare driver-class-name?

Normally **not necessary** if the JDBC URL is of a type Spring Boot recognizes and the corresponding driver is on the classpath.

PostgreSQL example:

    spring.datasource.url=jdbc:postgresql://localhost:5432/inventory
    spring.datasource.username=app_user
    spring.datasource.password=local-dev-password

With the PostgreSQL driver dependency present, Boot can infer the driver from the URL. If you need to declare it explicitly:

    spring.datasource.driver-class-name=org.postgresql.Driver

H2 has the driver:

    spring.datasource.driver-class-name=org.h2.Driver

Declaring driver-class-name does not download the dependency from Maven/Gradle. It only indicates which class the application needs to load; if the class does not exist, the application still fails.

### 7.2. Role of DataSourceProperties

DataSourceProperties has the prefix spring.datasource and provides methods such as:

- determineUrl(): determines the connection URL.
- determineDriverClassName(): determines the driver class.
- determineUsername() / determinePassword(): determines credentials.
- initializeDataSourceBuilder(): initializes a DataSourceBuilder from the bound properties.
- getEmbeddedDatabaseConnection(): indicates the selected embedded database connection.

Practical rules:

1. If the URL is configured, Boot uses that URL.
2. If the driver class is configured explicitly, the class must be loadable.
3. If the driver class is not configured, Boot attempts to infer the driver from the JDBC URL or the selected embedded database.
4. If a suitable URL/driver cannot be determined, DataSource creation fails with a configuration/driver error.

Do not add driver-class-name just to “try making it run”. Check the URL and dependencies first; declare the class explicitly only when needed or when using a special driver.

### 7.3. The driver must be on the runtime classpath

In Maven, database drivers are typically declared with runtime scope:

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

H2:

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

If the driver is only declared in test scope, the application may pass tests but lack the driver at runtime.

Modern JDBC drivers usually self-register via JDBC's service provider mechanism. Normal applications do not need to call Class.forName(driver) manually; what matters is that the driver JAR is on the classpath and the URL is valid.

### 7.4. Driver and pool are two separate dependencies

| Case | Pool | Driver | Result |
|---|---|---|---|
| Hikari + PostgreSQL driver + PostgreSQL URL | Yes | Yes | Can create pooled DataSource |
| Hikari + PostgreSQL URL but missing driver | Yes | No | Cannot connect; DataSource/connection creation fails |
| PostgreSQL driver but no pool and no type | No | Yes | Not eligible for pooled branch; embedded branch unsuitable for external URL |
| H2 engine + Hikari + no URL | Yes | H2 driver included in same dependency | Usually creates HikariDataSource connecting to in-memory H2 |
| H2 engine + no pool + no URL | No | H2 driver present | Can enter EmbeddedDatabaseConfiguration |

## 8. Important properties and what they control

| Property | Controls | Does not mean |
|---|---|---|
| spring.datasource.url | JDBC target | Does not select the connection pool |
| spring.datasource.driver-class-name | JDBC driver class | Does not add the driver JAR to the classpath |
| spring.datasource.type | DataSource implementation class | Does not select the database engine |
| spring.datasource.username/password | Authentication credentials | Does not decide embedded vs. pooled branch |
| spring.datasource.embedded-database-connection | Selected embedded engine or none | Does not force an EmbeddedDatabase bean if a pool is present |
| spring.datasource.generate-unique-name | Generated embedded database name | Does not automatically create an external database server |
| spring.datasource.jndi-name | Obtain DataSource from JNDI | When using JNDI, normal URL/driver/username/password are ignored |
| spring.datasource.hikari.* | HikariCP-specific settings | Has no effect if another pool is selected |

Do not confuse these three properties:

- **url** selects the database target.
- **driver-class-name** selects the driver.
- **type** selects the DataSource/connection pool implementation.

## 9. Runnable example: Spring Boot 3.3, Java 17, and H2

This example uses spring-boot-starter-jdbc and H2. The JDBC starter brings HikariCP onto the classpath. No URL is declared so Boot automatically picks in-memory H2. Because Hikari is present, the pooled branch is chosen; the created DataSource is HikariDataSource and connects to H2.

### 9.1. Project structure

    jdbc-classpath-demo/
    ├── pom.xml
    └── src/
        └── main/
            ├── java/demo/jdbc/
            │   └── JdbcClasspathDemo.java
            └── resources/
                └── application.properties

### 9.2. pom.xml

    <?xml version="1.0" encoding="UTF-8"?>
    <project xmlns="http://maven.apache.org/POM/4.0.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                                 https://maven.apache.org/xsd/maven-4.0.0.xsd">
        <modelVersion>4.0.0</modelVersion>

        <parent>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-parent</artifactId>
            <version>3.3.13</version>
            <relativePath/>
        </parent>

        <groupId>demo</groupId>
        <artifactId>jdbc-classpath-demo</artifactId>
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

### 9.3. application.properties

    spring.datasource.embedded-database-connection=h2
    spring.datasource.generate-unique-name=true

Do not set spring.datasource.url in this example. Boot can detect the H2 engine on the classpath and generate an in-memory URL. Because starter-jdbc pulls in HikariCP, the DataSource implementation is Hikari.

### 9.4. JdbcClasspathDemo.java

    package demo.jdbc;

    import java.sql.Connection;
    import java.sql.DatabaseMetaData;
    import javax.sql.DataSource;

    import org.springframework.boot.CommandLineRunner;
    import org.springframework.boot.SpringApplication;
    import org.springframework.boot.autoconfigure.SpringBootApplication;
    import org.springframework.jdbc.core.JdbcTemplate;

    @SpringBootApplication
    public class JdbcClasspathDemo implements CommandLineRunner {

        private final DataSource dataSource;
        private final JdbcTemplate jdbcTemplate;

        public JdbcClasspathDemo(
                DataSource dataSource,
                JdbcTemplate jdbcTemplate) {
            this.dataSource = dataSource;
            this.jdbcTemplate = jdbcTemplate;
        }

        public static void main(String[] args) {
            SpringApplication.run(JdbcClasspathDemo.class, args);
        }

        @Override
        public void run(String... args) throws Exception {
            jdbcTemplate.execute(
                    "create table demo_item (" +
                    "id bigint generated by default as identity primary key, " +
                    "name varchar(100) not null)");

            jdbcTemplate.update(
                    "insert into demo_item(name) values (?)",
                    "JDBC works");

            String value = jdbcTemplate.queryForObject(
                    "select name from demo_item where id = 1",
                    String.class);

            try (Connection connection = dataSource.getConnection()) {
                DatabaseMetaData metadata = connection.getMetaData();

                System.out.println(
                        "dataSourceType=" +
                        dataSource.getClass().getSimpleName());
                System.out.println(
                        "databaseProduct=" +
                        metadata.getDatabaseProductName());
                System.out.println(
                        "driverName=" +
                        metadata.getDriverName());
            }

            System.out.println("queryResult=" + value);
        }
    }

### 9.5. Running the program

From the directory containing pom.xml, you need JDK 17+ and Maven:

    mvn -q spring-boot:run

Lines printed by the program:

    dataSourceType=HikariDataSource
    databaseProduct=H2
    driverName=H2 JDBC Driver
    queryResult=JDBC works

Spring Boot may also output startup logs. The four lines above are the output produced by the program's System.out.println statements.

### 9.6. Why is the result HikariDataSource instead of EmbeddedDatabase?

1. spring-boot-starter-jdbc brings HikariCP onto the classpath.
2. PooledDataSourceCondition matches because DataSourceBuilder finds Hikari.
3. EmbeddedDatabaseCondition does not match because the pooled condition already matched.
4. DataSourceProperties detects the embedded H2 engine and determines the in-memory URL.
5. DataSourceConfiguration.Hikari creates HikariDataSource.
6. Hikari obtains connections via the H2 JDBC driver; JdbcTemplate executes SQL through the DataSource.

The example proves that **an embedded H2 engine can be used underneath a pooled DataSource**. “Embedded database” does not automatically mean “a DataSource bean of type EmbeddedDatabase”.

## 10. When does it take the EmbeddedDatabaseConfiguration branch directly?

For Boot to use the EmbeddedDatabaseConfiguration branch, all of the following must be satisfied simultaneously:

- spring-jdbc is present so DataSourceAutoConfiguration passes the classpath condition.
- A suitable embedded engine is present, such as H2.
- spring.datasource.url has no value containing text.
- No supported pool is on the classpath and spring.datasource.type is not set.
- No user-provided DataSource or XADataSource bean exists yet.

In the demo application, if you want to try this branch, you can remove the spring-boot-starter-jdbc dependency (which pulls in Hikari) and use spring-boot-starter together with spring-jdbc directly, while keeping H2 on the runtime classpath. Make sure the dependency tree does not pull in another pool through another starter or library.

Then PooledDataSourceCondition does not match; EmbeddedDatabaseCondition can match and Boot creates an EmbeddedDatabase using Spring JDBC.

This is an illustrative configuration to understand the internal branch. For applications needing a pool to handle real workloads, typically keep starter-jdbc and use a pooled DataSource.

## 11. External database configuration example: PostgreSQL

When switching from H2 to PostgreSQL, you need to change the engine/driver and URL. Dependency example:

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

Configuration:

    spring.datasource.url=jdbc:postgresql://localhost:5432/inventory
    spring.datasource.username=app_user
    spring.datasource.password=local-dev-password

With the PostgreSQL driver dependency present, Boot can infer the driver from the URL. If you want to declare it explicitly:

    spring.datasource.driver-class-name=org.postgresql.Driver

When Hikari is on the classpath, Boot selects the pooled branch. A non-empty PostgreSQL URL also prevents the embedded branch from matching. Hikari manages connections, and the PostgreSQL driver communicates with the PostgreSQL server.

Do not put real passwords in source control. Use environment variables, a secret store, or an appropriate secret management mechanism.

### 11.1. Changed URL but forgot the driver

Common symptoms:

- Added spring-boot-starter-jdbc.
- Set jdbc:postgresql://...
- The application reports that it cannot determine or load the driver class.

The usual cause is that the org.postgresql:postgresql dependency is missing, only in test scope, or not packaged in the runtime classpath. Add the driver at a version compatible with Spring Boot's dependency management.

### 11.2. Wrong driver class configured

If you configure:

    spring.datasource.driver-class-name=com.mysql.jdbc.Driver

but the current dependency/driver does not provide that class, Spring Boot cannot load the class. With modern MySQL Connector/J, the class commonly used is com.mysql.cj.jdbc.Driver. It is best to let Boot infer the driver from the URL whenever possible.

## 12. Branch decision table by classpath and configuration

| Classpath / configuration | Expected branch | Resulting DataSource |
|---|---|---|
| spring-jdbc + H2, no URL, no pool | Embedded | EmbeddedDatabase |
| spring-boot-starter-jdbc + H2, no URL | Pooled | HikariDataSource pointing to in-memory H2 |
| spring-boot-starter-jdbc + PostgreSQL driver + PostgreSQL URL | Pooled | HikariDataSource pointing to PostgreSQL |
| Hikari present, PostgreSQL URL, missing PostgreSQL driver | Pooled selected, but initialization/connection fails | No successful connection |
| H2 present, H2 URL, no pool and no type | Embedded blocked by URL; pooled does not match | Boot does not create a DataSource via the two default branches |
| spring.datasource.type set with valid DataSource class | Pooled | The specified implementation |
| Application-created DataSource bean present | Both default branches back off | User's DataSource |
| R2DBC ConnectionFactory bean present | Default DataSourceAutoConfiguration backs off | No automatic JDBC DataSource from this branch |
| Both H2 and PostgreSQL driver present, no URL | Need to determine suitable embedded engine | Use spring.datasource.embedded-database-connection to select embedded engine |
| spring.datasource.embedded-database-connection=none and no URL | No embedded engine selected | Need URL/driver or custom DataSource configuration |

The table reflects predictions under Boot 3.3.13 default conditions. Another auto-configuration, JNDI, custom DataSource, XADataSource, or other classpath conditions may alter the outcome.

## 13. JNDI and user-provided DataSource

Not every application lets Boot create the DataSource automatically.

### 13.1. JNDI DataSource

When running inside an application server, you can use a server-managed DataSource:

    spring.datasource.jndi-name=java:jboss/datasources/inventory

With JNDI, Boot looks up the DataSource by name. Normal URL, driver-class-name, username, and password properties are ignored because the server manages the connection configuration.

JndiDataSourceAutoConfiguration is a separate branch; do not confuse it with EmbeddedDatabaseConfiguration or PooledDataSourceConfiguration.

### 13.2. Declaring a DataSource bean manually

Illustrative example:

    @Configuration(proxyBeanMethods = false)
    public class CustomJdbcConfiguration {

        @Bean
        DataSource dataSource() {
            return DataSourceBuilder.create()
                    .url("jdbc:h2:mem:custom")
                    .username("sa")
                    .password("")
                    .driverClassName("org.h2.Driver")
                    .build();
        }
    }

This snippet requires importing DataSourceBuilder, DataSource, Configuration, and having the H2 driver on the classpath. In real applications, use DataSourceProperties/ConfigurationProperties when standard binding and consistent defaults are needed.

When a matching DataSource bean exists, the ConditionalOnMissingBean condition on the default branches stops Boot from creating an additional DataSource. That avoids having two DataSources competing for the same role.

## 14. Debugging: reading the Condition Evaluation Report and dependency tree

If you do not see a DataSource bean, check in order:

1. **Classpath:** Is spring-jdbc present? Is an embedded engine or corresponding vendor driver present? Is Hikari/Tomcat/DBCP2/UCP present?
2. **Dependency scope:** Is the driver on the runtime or compile classpath, not just test scope?
3. **Properties:** What values do spring.datasource.url, driver-class-name, type, and embedded-database-connection have?
4. **Custom beans:** Does the application already have a DataSource/XADataSource bean or an R2DBC ConnectionFactory bean?
5. **Condition Evaluation Report:** Run the application with --debug to see whether DataSourceAutoConfiguration, PooledDataSourceConfiguration, and EmbeddedDatabaseConfiguration match.
6. **Initialization errors:** If conditions matched, read exceptions about driver, URL, pool, or connection; a condition match does not guarantee the database server is reachable.
7. **Dependency tree:** Use mvn dependency:tree or Gradle dependencies to verify whether the driver/pool is actually in the runtime graph.

Some useful condition messages:

| Condition | Meaning to look for |
|---|---|
| ConditionalOnClass on DataSourceAutoConfiguration | Whether JDBC API and EmbeddedDatabaseType are on the classpath |
| ConditionalOnMissingBean type io.r2dbc.spi.ConnectionFactory | Whether an R2DBC ConnectionFactory caused JDBC auto-config to back off |
| PooledDataSourceCondition | Whether spring.datasource.type or a supported pool is on the classpath |
| EmbeddedDatabaseCondition | Whether URL is set, pooled branch matched, and embedded engine is found |
| ConditionalOnMissingBean DataSource/XADataSource | Whether the application already registered a DataSource or XADataSource |

Enabling --debug does not turn every logger to DEBUG; it adds the Condition Evaluation Report to explain auto-configuration decisions. If using Actuator with the endpoint exposed, /actuator/conditions also shows positive/negative matches.

## 15. Common mistakes

| Symptom | Cause | How to fix |
|---|---|---|
| H2 dependency present, but no DataSource | Missing spring-jdbc or another condition did not match | Check starters and the Condition Evaluation Report |
| Hikari present, but driver-not-found error | Pool is present, but vendor driver is missing | Add the driver JAR at runtime |
| driver-class-name set, but ClassNotFound | Wrong class name or missing dependency | Check the driver artifact and class name |
| Using starter-jdbc + H2, expecting EmbeddedDatabase bean | Hikari is present so the pooled branch takes priority | Check the bean type; HikariDataSource can use in-memory H2 |
| H2 URL set, but embedded branch does not match | EmbeddedDatabaseCondition skips when URL has text | If using a pool, the pooled branch handles the URL; for direct embedded branch, omit URL and remove pool |
| Both H2 and HSQL on classpath, wrong engine picked | Boot detects multiple embedded databases | Set spring.datasource.embedded-database-connection |
| embedded-database-connection=none set, and no URL | Embedded detection disabled, leaving no URL to connect | Declare external URL/driver or configure custom DataSource |
| spring.datasource.type set, but class missing | Type cannot be loaded | Add the dependency or fix the class name |
| Custom DataSource present, Boot still does not create default bean | Expected back-off behavior | Use the custom bean or remove it if you want Boot to manage it |
| R2DBC ConnectionFactory present, expecting Boot to create JDBC DataSource | Outer DataSourceAutoConfiguration backs off | Decide explicitly whether to use both blocking JDBC and R2DBC |
| Test app shares the same H2 database across contexts | Database name is not unique | Set spring.datasource.generate-unique-name=true |
| DataSource bean created, but queries fail | Server not running, wrong URL/credentials, or network blocked | Check the actual connection and exception metadata |

## 16. Self-check exercises

**Question 1.** An application has spring-boot-starter-jdbc and H2, with no URL declared. Is the DataSource bean usually EmbeddedDatabase or HikariDataSource?

**Answer:** HikariDataSource in the default configuration, because starter-jdbc pulls HikariCP onto the classpath and the pooled branch takes priority. H2 is still the database engine used underneath.

**Question 2.** HikariCP is present, but the PostgreSQL driver is missing; can Boot still select the pooled branch?

**Answer:** Yes. The pool on the classpath can make PooledDataSourceCondition match, but when determining the driver or creating a PostgreSQL connection, the application fails due to the missing driver.

**Question 3.** Only org.postgresql:postgresql is added, without spring-jdbc and without creating a custom DataSource; does Boot satisfy the conditions for DataSourceAutoConfiguration?

**Answer:** No. DataSourceAutoConfiguration also requires EmbeddedDatabaseType on the classpath; that class comes from Spring JDBC.

**Question 4.** H2 is on the classpath, no URL, no pool, no type. Which branch can match?

**Answer:** EmbeddedDatabaseConfiguration, provided there is no DataSource/XADataSource bean yet and the H2 engine is detected.

**Question 5.** spring.datasource.url has a value, but there is no pool and spring.datasource.type is not set. Will the embedded branch create a database?

**Answer:** No. A URL with text prevents EmbeddedDatabaseCondition from matching; the pooled branch also does not match without a pool/type. You need to add a pool/type or configure the DataSource manually.

**Question 6.** Does the spring.datasource.type property select the driver?

**Answer:** No. It selects the DataSource implementation. The driver is determined from driver-class-name, the JDBC URL, or a suitable embedded database.

**Question 7.** The application already has an R2DBC ConnectionFactory bean. Why is JDBC DataSource auto-config not appearing?

**Answer:** DataSourceAutoConfiguration has ConditionalOnMissingBean with type io.r2dbc.spi.ConnectionFactory, so by default it backs off when an R2DBC bean is present.

**Question 8.** When using H2 in tests with multiple application contexts, how do you avoid accidentally sharing a database with the same name?

**Answer:** Set spring.datasource.generate-unique-name=true so each context gets its own embedded database name.

## 17. Key points to remember

- **JDBC API, driver, database engine, and connection pool are four distinct components.**
- DataSourceAutoConfiguration requires the DataSource API and Spring JDBC EmbeddedDatabaseType on the classpath, and backs off when an R2DBC ConnectionFactory is present.
- The pooled branch matches when spring.datasource.type is set or a supported pool is on the classpath.
- The embedded branch requires an empty URL, the pooled branch not matching, and an embedded engine detected.
- With spring-boot-starter-jdbc, Hikari is usually present; H2 can be used as the engine while the DataSource bean is still HikariDataSource.
- The driver is usually inferred from the JDBC URL; the driver JAR must exist on the runtime classpath.
- spring.datasource.url selects the database target, driver-class-name selects the driver, and type selects the DataSource implementation.
- If the condition matches but connecting fails, check the driver, URL, credentials, network, and database server.

### Official documentation

- Spring Boot 3.3 — SQL Databases: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
- Spring Boot 3.3 — DataSourceAutoConfiguration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.3 — DataSourceProperties API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- Spring Boot 3.3 — EmbeddedDatabaseConfiguration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.EmbeddedDatabaseConfiguration.html
- Spring Boot 3.3 — PooledDataSourceConfiguration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.PooledDataSourceConfiguration.html
- Spring Framework — Embedded Database Support: https://docs.spring.io/spring-framework/reference/data-access/jdbc/embedded-database-support.html
